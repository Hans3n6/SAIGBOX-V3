from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
import json
import asyncio

from api.auth import get_current_user
from api.models import ChatMessage, ChatResponse, QuickReplyRequest, QuickReplyResponse
from core.database import get_db, User, ChatHistory, Email as EmailModel
from core.saig_assistant import SAIGAssistant

router = APIRouter()
saig = SAIGAssistant()

@router.post("/chat", response_model=ChatResponse)
async def chat_with_saig(
    message: ChatMessage,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send message to SAIG assistant"""
    try:
        # Process message with SAIG
        result = await saig.process_message(
            db=db,
            user=current_user,
            message=message.message,
            context=message.context
        )
        
        return ChatResponse(
            response=result["response"],
            actions_taken=result.get("actions_taken", []),
            context=result.get("context", {})
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_chat_history(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get chat history with SAIG"""
    history = db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.id
    ).order_by(ChatHistory.created_at.desc()).limit(limit).all()
    
    # Reverse to get chronological order
    history.reverse()
    
    return [
        {
            "id": h.id,
            "role": h.role,
            "message": h.message,
            "created_at": h.created_at.isoformat()
        }
        for h in history
    ]

@router.delete("/history")
async def clear_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clear chat history"""
    db.query(ChatHistory).filter(
        ChatHistory.user_id == current_user.id
    ).delete()
    db.commit()
    
    return {"success": True, "message": "Chat history cleared"}

@router.post("/execute")
async def execute_command(
    command: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Execute a SAIG command directly"""
    # This endpoint allows direct command execution
    # Useful for UI buttons that trigger specific SAIG actions
    
    command_type = command.get("type")
    params = command.get("params", {})
    
    if command_type == "summarize_emails":
        message = "Summarize my recent emails"
    elif command_type == "create_action":
        message = f"Create an action item: {params.get('title', 'New Task')}"
    elif command_type == "mark_all_read":
        message = "Mark all emails as read"
    elif command_type == "search":
        message = f"Search for emails about {params.get('query', '')}"
    else:
        raise HTTPException(status_code=400, detail="Unknown command type")
    
    # Process with SAIG
    result = await saig.process_message(
        db=db,
        user=current_user,
        message=message,
        context=params
    )
    
    return {
        "success": True,
        "response": result["response"],
        "actions_taken": result.get("actions_taken", [])
    }

@router.post("/quick-reply", response_model=QuickReplyResponse)
async def generate_quick_reply(
    request: QuickReplyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a quick reply based on action type (accept, decline, schedule_call, acknowledge)"""
    try:
        # Get the email
        email = db.query(EmailModel).filter(
            EmailModel.id == request.email_id,
            EmailModel.user_id == current_user.id
        ).first()

        if not email:
            raise HTTPException(status_code=404, detail="Email not found")

        # Generate quick reply using SAIG
        reply_text = await saig.generate_quick_reply(
            action_type=request.action_type,
            email_context={
                "id": email.id,
                "subject": email.subject,
                "sender": email.sender,
                "sender_name": email.sender_name,
                "body": email.body_text or email.snippet or "",
                "received_at": email.received_at.isoformat() if email.received_at else None
            },
            custom_note=request.custom_note,
            user=current_user,
            db=db
        )

        # Extract recipient email
        recipient = email.sender
        if recipient and '<' in recipient:
            import re
            match = re.search(r'<([^>]+)>', recipient)
            if match:
                recipient = match.group(1)

        # Build subject
        subject = email.subject or ""
        if not subject.startswith("Re:"):
            subject = f"Re: {subject}"

        return QuickReplyResponse(
            reply_text=reply_text,
            subject=subject,
            recipient=recipient,
            can_send_immediately=True
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat/stream")
async def chat_with_saig_stream(
    message: ChatMessage,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stream SAIG responses for faster perceived speed"""
    async def generate():
        try:
            # Process message with SAIG (full response)
            result = await saig.process_message(
                db=db,
                user=current_user,
                message=message.message,
                context=message.context
            )

            response_text = result.get("response", "")

            # Stream the response in chunks for perceived speed
            chunk_size = 50
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i + chunk_size]
                yield f"data: {json.dumps({'chunk': chunk, 'done': False})}\n\n"
                await asyncio.sleep(0.02)  # Small delay between chunks

            # Send final message with full context
            yield f"data: {json.dumps({'chunk': '', 'done': True, 'actions_taken': result.get('actions_taken', [])})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )