from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
import re
import logging

from api.auth import get_current_user
from api.models import *
from core.database import get_db, User, Email as EmailModel, ActionItem, UrgencyPattern
from core.gmail_service import GmailService
from core.token_manager import token_manager
from core.saig_assistant import SAIGAssistant
from core.urgency_detector import UrgencyDetector
from core.semantic_search import semantic_search
import asyncio
import os

router = APIRouter()
gmail_service = GmailService()
saig_assistant = SAIGAssistant()
logger = logging.getLogger(__name__)

# Queue for processing urgent emails
urgent_email_queue = asyncio.Queue()
processing_urgent = False

def clean_email_data(emails):
    """Clean email data to ensure lists are not None"""
    for email in emails:
        if email.labels is None:
            email.labels = []
        if email.attachments is None:
            email.attachments = []
        if email.recipients is None:
            email.recipients = []
        if email.cc is None:
            email.cc = []
        if email.bcc is None:
            email.bcc = []
    return emails

@router.get("/", response_model=EmailListResponse)
async def list_emails(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    sender: Optional[str] = Query(None, description="Filter by sender email address"),
    semantic: bool = Query(True, description="Use semantic search"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List emails with pagination and search (semantic or keyword)"""

    # If filtering by sender, skip semantic search and do direct filter
    if sender:
        query = db.query(EmailModel).filter(
            EmailModel.user_id == current_user.id,
            EmailModel.deleted_at.is_(None),
            EmailModel.sender.ilike(f"%{sender}%")
        )
        total = query.count()
        offset = (page - 1) * limit
        emails = query.order_by(EmailModel.received_at.desc()).offset(offset).limit(limit).all()
        emails = clean_email_data(emails)
        pages = (total + limit - 1) // limit if total > 0 else 1

        return EmailListResponse(
            emails=emails,
            total=total,
            page=page,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1
        )

    # Apply search filter
    if search and semantic:
        # Semantic search using AI-powered relevance scoring
        emails = await perform_semantic_search(db, current_user.id, search, limit, page)
        total = len(emails)
        pages = 1  # Semantic search returns best matches in one page

        return EmailListResponse(
            emails=emails,
            total=total,
            page=page,
            pages=pages,
            has_next=False,  # Semantic search doesn't use infinite scroll
            has_prev=False
        )

    # Standard query for keyword search or no search
    query = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.deleted_at.is_(None)
    )

    # Apply keyword search filter
    if search and not semantic:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                EmailModel.subject.ilike(search_term),
                EmailModel.sender.ilike(search_term),
                EmailModel.body_text.ilike(search_term),
                EmailModel.snippet.ilike(search_term)
            )
        )
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    emails = query.order_by(EmailModel.received_at.desc()).offset(offset).limit(limit).all()
    
    # Clean email data
    emails = clean_email_data(emails)
    
    # Calculate pagination info
    pages = (total + limit - 1) // limit
    
    # Return actual pagination state
    # Frontend will handle infinite scroll logic
    return EmailListResponse(
        emails=emails,
        total=total,
        page=page,
        pages=pages,
        has_next=page < pages,  # Return actual state
        has_prev=page > 1
    )

@router.get("/sent", response_model=EmailListResponse)
async def list_sent_emails(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List sent emails with pagination and search"""
    query = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.sender == current_user.email,
        EmailModel.deleted_at.is_(None)
    )
    
    # Apply search filter
    if search:
        query = query.filter(
            (EmailModel.subject.contains(search)) |
            (EmailModel.body_text.contains(search))
        )
    
    # Get total count
    total = query.count()
    
    # Apply pagination
    offset = (page - 1) * limit
    emails = query.order_by(EmailModel.received_at.desc()).offset(offset).limit(limit).all()
    
    # Clean email data
    emails = clean_email_data(emails)
    
    # Calculate pagination info
    pages = (total + limit - 1) // limit
    
    # Return actual pagination state
    # Frontend will handle infinite scroll logic
    return EmailListResponse(
        emails=emails,
        total=total,
        page=page,
        pages=pages,
        has_next=page < pages,  # Return actual state
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

    # Convert None values to empty lists for Pydantic model compatibility
    return Email(
        id=email.id,
        gmail_id=email.gmail_id,
        thread_id=email.thread_id,
        subject=email.subject,
        sender=email.sender,
        sender_name=email.sender_name,
        recipients=email.recipients or [],
        cc=email.cc or [],
        bcc=email.bcc or [],
        body_text=email.body_text,
        body_html=email.body_html,
        snippet=email.snippet,
        labels=email.labels or [],
        is_read=email.is_read or False,
        is_starred=email.is_starred or False,
        is_urgent=email.is_urgent or False,
        urgency_score=email.urgency_score or 0,
        urgency_reason=email.urgency_reason,
        has_attachments=email.has_attachments or False,
        attachments=email.attachments or [],
        received_at=email.received_at,
        created_at=email.created_at or datetime.utcnow(),
        updated_at=email.updated_at or email.created_at or datetime.utcnow()
    )

@router.get("/{email_id}/suggestions")
async def get_email_suggestions(
    email_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get smart reply suggestions for an email"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    # Analyze email and generate suggestions
    suggestions = generate_email_suggestions(
        subject=email.subject or "",
        sender=email.sender or "",
        sender_name=email.sender_name or "",
        body=email.body_text or email.snippet or ""
    )

    return {
        "suggestions": suggestions,
        "email_analysis": {
            "is_question": any(s["intent"] == "question" for s in suggestions),
            "is_request": any(s["intent"] in ["accept", "decline"] for s in suggestions),
            "is_scheduling": any(s["intent"] == "schedule" for s in suggestions),
            "suggested_action": suggestions[0]["intent"] if suggestions else None
        }
    }

def generate_email_suggestions(subject: str, sender: str, sender_name: str, body: str) -> list:
    """Generate smart reply suggestions based on email content analysis."""
    suggestions = []
    body_lower = body.lower()
    subject_lower = subject.lower()

    # Extract first name
    first_name = sender_name.split()[0] if sender_name else "there"
    if not first_name or first_name == "there":
        if sender and '<' in sender:
            first_name = sender.split('<')[0].strip().strip('"').split()[0]
        elif sender:
            first_name = sender.split('@')[0].capitalize()

    # Detect email intent and generate appropriate suggestions
    is_question = '?' in body or any(q in body_lower for q in ['could you', 'can you', 'would you', 'do you', 'are you', 'have you', 'what', 'when', 'where', 'how', 'why'])
    is_meeting_request = any(m in body_lower for m in ['meeting', 'schedule', 'call', 'available', 'calendar', 'time to chat', 'discuss'])
    is_request = any(r in body_lower for r in ['please', 'could you', 'can you', 'would you mind', 'need you to', 'request'])
    is_info_share = any(i in body_lower for i in ['fyi', 'for your information', 'wanted to share', 'letting you know', 'update', 'attached'])
    is_thank_you = any(t in body_lower for t in ['thank you', 'thanks', 'appreciate'])

    # Generate contextual suggestions
    if is_meeting_request:
        suggestions.append({
            "text": f"Hi {first_name},\n\nI'd be happy to schedule a call. I'm available [suggest times]. Let me know what works best for you.\n\nBest regards",
            "intent": "schedule",
            "tone": "professional",
            "confidence": 0.9
        })
        suggestions.append({
            "text": f"Hi {first_name},\n\nThank you for reaching out. Unfortunately, my schedule is quite full at the moment. Could we revisit this next week?\n\nBest regards",
            "intent": "defer",
            "tone": "professional",
            "confidence": 0.7
        })

    if is_request:
        suggestions.append({
            "text": f"Hi {first_name},\n\nAbsolutely, I'll take care of this right away. You can expect an update shortly.\n\nBest regards",
            "intent": "accept",
            "tone": "professional",
            "confidence": 0.85
        })
        suggestions.append({
            "text": f"Hi {first_name},\n\nI appreciate you reaching out. Unfortunately, I won't be able to accommodate this request at this time. Let me know if there's another way I can help.\n\nBest regards",
            "intent": "decline",
            "tone": "professional",
            "confidence": 0.75
        })

    if is_question:
        suggestions.append({
            "text": f"Hi {first_name},\n\nThank you for your question. Let me look into this and get back to you with a detailed response.\n\nBest regards",
            "intent": "question",
            "tone": "professional",
            "confidence": 0.8
        })

    if is_info_share or is_thank_you:
        suggestions.append({
            "text": f"Hi {first_name},\n\nThank you for sharing this. I've noted the information and will follow up if I have any questions.\n\nBest regards",
            "intent": "acknowledge",
            "tone": "professional",
            "confidence": 0.8
        })

    # Always add a generic acknowledgment as fallback
    if len(suggestions) < 3:
        suggestions.append({
            "text": f"Hi {first_name},\n\nThank you for your email. I've received your message and will review it shortly.\n\nBest regards",
            "intent": "acknowledge",
            "tone": "professional",
            "confidence": 0.7
        })

    # Limit to top 4 suggestions
    return suggestions[:4]

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
    
    # Update in Gmail (skip for demo emails)
    if email.gmail_id and not email.is_read and not email.gmail_id.startswith("demo_"):
        success = gmail_service.mark_as_read(current_user, email.gmail_id)
        if not success:
            logger.warning(f"Failed to mark email {email.gmail_id} as read in Gmail")
            # Don't fail the request - just update locally

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
    
    # Update in Gmail (skip for demo emails)
    if email.gmail_id and email.is_read and not email.gmail_id.startswith("demo_"):
        success = gmail_service.mark_as_unread(current_user, email.gmail_id)
        if not success:
            logger.warning(f"Failed to mark email {email.gmail_id} as unread in Gmail")
            # Don't fail the request - just update locally

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

    # Update in Gmail (skip for demo emails)
    if email.gmail_id and not email.gmail_id.startswith("demo_"):
        if new_status:
            success = gmail_service.star_email(current_user, email.gmail_id)
        else:
            success = gmail_service.unstar_email(current_user, email.gmail_id)

        if not success:
            logger.warning(f"Failed to {'star' if new_status else 'unstar'} email {email.gmail_id} in Gmail")
            # Don't fail the request - just update locally

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
            # Log the error but don't fail completely
            logger.error(f"Failed to move email {email.gmail_id} to Gmail trash, will mark as deleted locally")

    # Delete associated action items
    deleted_actions = db.query(ActionItem).filter(
        ActionItem.email_id == email_id
    ).delete(synchronize_session=False)
    if deleted_actions > 0:
        logger.info(f"Deleted {deleted_actions} action items associated with email {email_id}")

    # Soft delete in database and update labels
    email.deleted_at = datetime.utcnow()

    # Update labels to reflect trash status
    if not email.labels:
        email.labels = []

    # Add TRASH label
    if 'TRASH' not in email.labels:
        email.labels.append('TRASH')

    # Remove INBOX label if present
    if 'INBOX' in email.labels:
        email.labels.remove('INBOX')

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

@router.post("/sync")
async def sync_emails(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Sync emails from Gmail with urgency detection"""
    try:
        # Initialize urgency detector
        urgency_detector = UrgencyDetector(db)
        
        # Fetch new emails from Gmail
        new_emails = gmail_service.fetch_recent_emails(current_user, limit=50)
        
        synced_count = 0
        urgent_count = 0
        
        for email_data in new_emails:
            # Check if email already exists
            existing = db.query(EmailModel).filter(
                EmailModel.gmail_id == email_data.get('gmail_id')
            ).first()
            
            if not existing:
                # Create new email record
                email = EmailModel(
                    user_id=current_user.id,
                    gmail_id=email_data.get('gmail_id'),
                    thread_id=email_data.get('thread_id'),
                    subject=email_data.get('subject'),
                    sender=email_data.get('sender'),
                    sender_name=email_data.get('sender_name'),
                    recipients=email_data.get('recipients'),
                    body_text=email_data.get('body_text'),
                    body_html=email_data.get('body_html'),
                    snippet=email_data.get('snippet'),
                    is_read=email_data.get('is_read', False),
                    is_starred=email_data.get('is_starred', False),
                    has_attachments=email_data.get('has_attachments', False),
                    attachments=email_data.get('attachments'),
                    received_at=email_data.get('received_at'),
                    labels=email_data.get('labels')
                )
                
                # Check urgency
                is_urgent, score, reason = urgency_detector.should_mark_urgent(email, current_user)
                
                if is_urgent:
                    email.is_urgent = True
                    email.urgency_score = score
                    email.urgency_reason = reason
                    urgent_count += 1
                    
                    # Add to urgent processing queue
                    await urgent_email_queue.put((email, current_user))
                
                db.add(email)
                synced_count += 1
        
        db.commit()
        
        # Start processing urgent emails if not already running
        if urgent_count > 0 and not processing_urgent:
            asyncio.create_task(process_urgent_emails(db))
        
        return {
            "success": True,
            "synced": synced_count,
            "urgent": urgent_count,
            "message": f"Synced {synced_count} new emails, {urgent_count} marked as urgent"
        }
        
    except Exception as e:
        logger.error(f"Error syncing emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def process_urgent_emails(db: Session):
    """Background task to process urgent emails through AI"""
    global processing_urgent
    processing_urgent = True
    
    batch_size = int(os.getenv('URGENCY_BATCH_SIZE', '5'))
    confidence_threshold = int(os.getenv('ACTION_CONFIDENCE_THRESHOLD', '70'))
    
    try:
        while not urgent_email_queue.empty():
            batch = []
            
            # Get batch of urgent emails
            for _ in range(min(batch_size, urgent_email_queue.qsize())):
                if not urgent_email_queue.empty():
                    batch.append(await urgent_email_queue.get())
            
            # Process each email
            for email, user in batch:
                try:
                    # Analyze with SAIG
                    analysis = await saig_assistant.analyze_urgent_email(email, db, user)
                    
                    # Update email with analysis results
                    email.urgency_analyzed_at = datetime.utcnow()
                    
                    # Create action items
                    created_items = []
                    for item_data in analysis.get('action_items', []):
                        if item_data['confidence'] >= confidence_threshold:
                            action_item = ActionItem(
                                user_id=user.id,
                                email_id=email.id,
                                title=item_data['title'],
                                description=item_data['description'],
                                due_date=item_data.get('due_date'),
                                priority={'high': 1, 'medium': 2, 'low': 3}.get(
                                    item_data.get('priority', 'medium'), 2
                                ),
                                auto_created=True,
                                confidence_score=item_data['confidence'],
                                source_quote=item_data.get('source_quote', '')
                            )
                            db.add(action_item)
                            created_items.append(action_item)
                    
                    if created_items:
                        email.auto_actions_created = True
                        email.action_count = len(created_items)
                        
                        # TODO: Send WebSocket notification to user
                        # await websocket_manager.send_action_items_created(
                        #     user.id, email, created_items
                        # )
                    
                    db.commit()
                    logger.info(f"Processed urgent email {email.id}: {len(created_items)} actions created")
                    
                except Exception as e:
                    logger.error(f"Error processing urgent email {email.id}: {e}")
                    continue
            
            # Wait before processing next batch
            await asyncio.sleep(int(os.getenv('URGENCY_PROCESSING_INTERVAL', '30')))
    
    finally:
        processing_urgent = False

@router.get("/urgent")
async def get_urgent_emails(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all urgent emails for current user"""
    emails = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.is_urgent == True,
        EmailModel.deleted_at.is_(None)
    ).order_by(
        EmailModel.urgency_score.desc(),
        EmailModel.received_at.desc()
    ).limit(limit).all()
    
    return {
        "emails": emails,
        "total": len(emails)
    }

@router.patch("/{email_id}/urgency")
async def update_email_urgency(
    email_id: str,
    urgency_update: Dict[str, bool],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually override urgency status"""
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    is_urgent = urgency_update.get('is_urgent', False)
    
    # Update urgency status
    email.is_urgent = is_urgent
    if not is_urgent:
        email.urgency_score = 0
        email.urgency_reason = "Manually marked as not urgent"
    else:
        email.urgency_reason = "Manually marked as urgent"
    
    db.commit()
    
    # Learn from correction
    urgency_detector = UrgencyDetector(db)
    urgency_detector.learn_from_correction(email, current_user, is_urgent)
    
    return {
        "success": True,
        "is_urgent": is_urgent
    }

@router.post("/urgency/learn")
async def learn_from_correction(
    correction_data: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update patterns based on user correction"""
    email_id = correction_data.get('email_id')
    corrected_to = correction_data.get('corrected_to')
    
    email = db.query(EmailModel).filter(
        EmailModel.id == email_id,
        EmailModel.user_id == current_user.id
    ).first()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    urgency_detector = UrgencyDetector(db)
    urgency_detector.learn_from_correction(email, current_user, corrected_to)
    
    return {"success": True, "message": "Pattern learning updated"}

@router.post("/urgent/process")
async def manually_process_urgent(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger urgent email processing"""
    # Get unprocessed urgent emails
    urgent_emails = db.query(EmailModel).filter(
        EmailModel.user_id == current_user.id,
        EmailModel.is_urgent == True,
        EmailModel.urgency_analyzed_at.is_(None),
        EmailModel.deleted_at.is_(None)
    ).limit(10).all()
    
    for email in urgent_emails:
        await urgent_email_queue.put((email, current_user))
    
    # Start processing if not already running
    if not processing_urgent and not urgent_email_queue.empty():
        asyncio.create_task(process_urgent_emails(db))
    
    return {
        "success": True,
        "queued": len(urgent_emails),
        "message": f"Queued {len(urgent_emails)} urgent emails for processing"
    }

async def perform_semantic_search(db: Session, user_id: str, query: str, limit: int, page: int) -> List[EmailModel]:
    """Perform AI-powered semantic search to find relevant emails"""
    return await semantic_search.search(db, user_id, query, limit, page)