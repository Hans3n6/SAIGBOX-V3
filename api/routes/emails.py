from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import re
import logging

from api.auth import get_current_user
from api.models import *
from core.database import get_db, User, Email as EmailModel
from core.gmail_service import GmailService
from core.token_manager import token_manager
from core.saig_assistant import SAIGAssistant

router = APIRouter()
gmail_service = GmailService()
logger = logging.getLogger(__name__)

@router.get("/", response_model=EmailListResponse)
async def list_emails(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List emails with pagination and search"""
    query = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    )
    
    # Apply search filter
    if search:
        query = query.filter(
            (EmailModel.subject.contains(search)) |
            (EmailModel.sender.contains(search)) |
            (EmailModel.body_text.contains(search))
        )
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    emails = query.order_by(EmailModel.received_at.desc()).offset(offset).limit(limit).all()
    
    # Calculate pagination info
    pages = (total + limit - 1) // limit
    
    return EmailListResponse(
        emails=emails,
        total=total,
        page=page,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1
    )

@router.get("/{email_id}", response_model=Email)
async def get_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get email details"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    return email

@router.put("/{email_id}/read")
async def mark_as_read(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark email as read"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Update in Gmail
    if email.gmail_id and not email.is_read:
        success = gmail_service.mark_as_read(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update Gmail")
    
    # Update in database
    email.is_read = True
    db.commit()
    
    return {"success": True, "message": "Email marked as read"}

@router.put("/{email_id}/unread")
async def mark_as_unread(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark email as unread"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Update in Gmail
    if email.gmail_id and email.is_read:
        success = gmail_service.mark_as_unread(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update Gmail")
    
    # Update in database
    email.is_read = False
    db.commit()
    
    return {"success": True, "message": "Email marked as unread"}

@router.put("/{email_id}/star")
async def star_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Star/unstar email"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Toggle star status
    new_status = not email.is_starred
    
    # Update in Gmail
    if email.gmail_id:
        if new_status:
            success = gmail_service.star_email(current_user, email.gmail_id)
        else:
            success = gmail_service.unstar_email(current_user, email.gmail_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update Gmail")
    
    # Update in database
    email.is_starred = new_status
    db.commit()
    
    return {
        "success": True,
        "message": f"Email {'starred' if new_status else 'unstarred'}",
        "is_starred": new_status
    }

@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Move email to trash"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Move to trash in Gmail
    if email.gmail_id:
        success = gmail_service.move_to_trash(current_user, email.gmail_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to trash email in Gmail")
    
    # Soft delete in database
    email.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "message": "Email moved to trash"}

@router.post("/compose", response_model=dict)
async def compose_email(
    email_data: EmailCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a new email"""
    try:
        # Send via Gmail
        result = gmail_service.send_email(
            current_user,
            email_data.to,
            email_data.subject,
            email_data.body,
            email_data.cc,
            email_data.bcc
        )
        
        # Save to database
        new_email = EmailModel(
            user_id=current_user.id,
            gmail_id=result.get('id'),
            subject=email_data.subject,
            sender=current_user.email,
            recipients=email_data.to,
            cc=email_data.cc or [],
            bcc=email_data.bcc or [],
            body_text=email_data.body,
            is_read=True,
            received_at=datetime.utcnow()
        )
        db.add(new_email)
        db.commit()
        
        return {
            "success": True,
            "message": "Email sent successfully",
            "email_id": new_email.id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reply", response_model=dict)
async def reply_to_email(
    reply_data: EmailReply,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reply to an email"""
    # Get original email
    original = db.query(EmailModel).filter(
        EmailModel.id == reply_data.email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not original:
        raise HTTPException(status_code=404, detail="Original email not found")
    
    # Prepare reply
    to = [original.sender]
    if reply_data.reply_all and original.recipients:
        to.extend([r for r in original.recipients if r != current_user.email])
    
    subject = original.subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    
    try:
        # Send reply with thread context
        if original.gmail_id and original.thread_id:
            # Use the reply_to_email method to maintain thread
            result = gmail_service.reply_to_email(
                user=current_user,
                original_message_id=original.gmail_id,
                thread_id=original.thread_id,
                to=original.sender,
                subject=subject,
                body=reply_data.body
            )
        else:
            # Fallback to regular send if no thread info
            result = gmail_service.send_email(
                current_user,
                to,
                subject,
                reply_data.body
            )
        
        return {
            "success": True,
            "message": "Reply sent successfully",
            "thread_id": original.thread_id if original.thread_id else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search", response_model=List[Email])
async def search_emails(
    search_query: SearchQuery,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search emails"""
    query = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    )
    
    # Build search conditions
    conditions = []
    if search_query.in_subject:
        conditions.append(EmailModel.subject.contains(search_query.query))
    if search_query.in_body:
        conditions.append(EmailModel.body_text.contains(search_query.query))
    if search_query.in_sender:
        conditions.append(EmailModel.sender.contains(search_query.query))
    
    if conditions:
        from sqlalchemy import or_
        query = query.filter(or_(*conditions))
    
    emails = query.order_by(EmailModel.received_at.desc()).limit(50).all()
    
    return emails

@router.post("/{email_id}/summary")
async def generate_email_summary(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate AI summary for an email"""
    try:
        # Get the email
        email = db.query(EmailModel).filter(
            EmailModel.id == email_id,
            EmailModel.user_id == current_user.id,
            EmailModel.deleted_at.is_(None)
        ).first()
        
        if not email:
            raise HTTPException(status_code=404, detail="Email not found")
        
        # Use SAIG Assistant to generate summary
        saig = SAIGAssistant()
        
        # Clean email text for summarization
        body_text = clean_email_text(email.body_text or email.snippet or "")
        
        # Generate AI summary using SAIG
        summary_result = await generate_ai_summary(
            saig=saig,
            subject=email.subject,
            sender=email.sender_name or email.sender,
            content=body_text,
            received_at=email.received_at
        )
        
        return summary_result
    
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def clean_email_text(text: str) -> str:
    """Clean email text for summarization"""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove email headers that might be in the body
    text = re.sub(r'^(From|To|Subject|Date|Sent):.*$', '', text, flags=re.MULTILINE)
    
    # Remove quoted text (lines starting with >)
    text = re.sub(r'^>.*$', '', text, flags=re.MULTILINE)
    
    # Remove email signatures (basic detection)
    text = re.sub(r'--\s*\n.*', '', text, flags=re.DOTALL)
    text = re.sub(r'Best regards.*', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'Sincerely.*', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    return text.strip()

async def generate_ai_summary(saig: SAIGAssistant, subject: str, sender: str, content: str, received_at: datetime) -> Dict:
    """Generate AI summary using SAIG Assistant"""
    
    # Truncate content to manage token usage
    clean_content = content[:3000] if content else ""
    
    # Format received date
    time_ago = ""
    if received_at:
        now = datetime.now(received_at.tzinfo) if received_at.tzinfo else datetime.now()
        diff = now - received_at
        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                minutes = diff.seconds // 60
                time_ago = f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                time_ago = f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.days == 1:
            time_ago = "yesterday"
        else:
            time_ago = f"{diff.days} days ago"
    
    prompt = f"""Analyze this email and provide a comprehensive summary:

From: {sender}
Subject: {subject}
Received: {time_ago}
Content: {clean_content}

Create a detailed summary with these sections:

**OVERVIEW**
Provide a 1-2 sentence summary of what this email is about.

**KEY POINTS**
• List the main points from the email (3-5 bullet points)
• Focus on the most important information

**ACTION ITEMS**
• What actions are requested or needed? (if any)
• Include any deadlines mentioned
• Note who needs to take action

**TONE & URGENCY**
• Describe the tone (formal, casual, urgent, friendly, etc.)
• Rate urgency: High / Medium / Low
• Note any emotional context

**SUGGESTED RESPONSE**
• How should you respond to this email?
• Key points to address in your reply
• Recommended tone for response

Format your response with clear sections and bullet points."""

    try:
        # Use SAIG to generate the summary
        summary_text = await saig._call_anthropic(prompt, max_tokens=600, temperature=0.3)
        
        if summary_text and "API error" not in summary_text:
            # Convert the markdown response to HTML
            html_content = convert_markdown_to_html(summary_text)
            
            # Extract urgency level from the summary
            urgency = "Normal"
            if re.search(r'urgency:\s*high', summary_text, re.IGNORECASE):
                urgency = "High"
            elif re.search(r'urgency:\s*medium', summary_text, re.IGNORECASE):
                urgency = "Medium"
            
            return {
                "summary": {
                    "type": "AI Analysis",
                    "urgency": urgency,
                    "has_ai_summary": True
                },
                "content": html_content
            }
        else:
            # Fallback to basic summary
            return generate_fallback_summary(subject, sender, clean_content)
            
    except Exception as e:
        logger.error(f"Error calling AI: {str(e)}")
        return generate_fallback_summary(subject, sender, clean_content)

def convert_markdown_to_html(text: str) -> str:
    """Convert markdown-formatted text to HTML with styling"""
    html = text
    
    # Convert headers (** text **)
    html = re.sub(r'\*\*([^*]+)\*\*', r'<h4 class="font-semibold text-gray-900 mb-2 mt-4">\1</h4>', html)
    
    # Convert bullet points to list items
    lines = html.split('\n')
    formatted_lines = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('•'):
            if not in_list:
                formatted_lines.append('<ul class="space-y-2 ml-4">')
                in_list = True
            formatted_lines.append(f'<li class="text-sm text-gray-700 flex items-start"><span class="text-green-500 mr-2">▸</span><span>{stripped[1:].strip()}</span></li>')
        else:
            if in_list and stripped:
                formatted_lines.append('</ul>')
                in_list = False
            if stripped and not stripped.startswith('<'):
                # Check if it's a section header
                if any(header in stripped for header in ['OVERVIEW', 'KEY POINTS', 'ACTION ITEMS', 'TONE', 'SUGGESTED']):
                    formatted_lines.append(f'<h4 class="font-semibold text-gray-900 mb-2 mt-4">{stripped}</h4>')
                else:
                    formatted_lines.append(f'<p class="text-sm text-gray-700 mb-2">{stripped}</p>')
    
    if in_list:
        formatted_lines.append('</ul>')
    
    # Wrap in a styled container with gradient background
    return f"""
    <div class="space-y-4">
        <div class="bg-gradient-to-r from-green-50 to-blue-50 p-4 rounded-lg border border-green-200">
            <div class="flex items-center mb-3">
                <i class="fas fa-brain text-green-600 mr-2"></i>
                <span class="text-xs font-semibold text-green-700">AI Summary powered by SAIG</span>
            </div>
            {''.join(formatted_lines)}
        </div>
    </div>
    """

def generate_fallback_summary(subject: str, sender: str, content: str) -> Dict:
    """Generate a basic summary when AI is not available"""
    
    # Extract first few sentences
    sentences = content.split('.')[:3]
    key_points = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
    
    # Basic urgency detection
    urgency = "Normal"
    lower_content = content.lower()
    if any(word in lower_content for word in ['urgent', 'asap', 'immediately', 'critical']):
        urgency = "High"
    
    html = f"""
    <div class="space-y-4">
        <div class="bg-yellow-50 p-3 rounded-lg text-sm border border-yellow-200">
            <i class="fas fa-info-circle text-yellow-600 mr-2"></i>
            <span class="text-yellow-700">Basic summary - AI analysis unavailable</span>
        </div>
        
        <div class="bg-gray-50 p-4 rounded-lg">
            <h4 class="font-semibold text-gray-900 mb-2">Email Overview</h4>
            <p class="text-sm text-gray-700 mb-2">From: {sender}</p>
            <p class="text-sm text-gray-700 mb-2">Subject: {subject}</p>
            
            <h4 class="font-semibold text-gray-900 mb-2 mt-4">Content Preview</h4>
            <ul class="space-y-1">
    """
    
    for point in key_points:
        html += f'<li class="text-sm text-gray-700 flex items-start"><span class="text-gray-500 mr-2">•</span><span>{point}</span></li>'
    
    html += f"""
            </ul>
            
            <div class="pt-3 mt-3 border-t border-gray-200 text-xs text-gray-600">
                <div>Urgency: <span class="{'text-red-600 font-semibold' if urgency == 'High' else 'text-gray-700'}">{urgency}</span></div>
            </div>
        </div>
    </div>
    """
    
    return {
        "summary": {
            "type": "Basic Analysis",
            "urgency": urgency,
            "has_ai_summary": False
        },
        "content": html
    }