from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from api.auth import get_current_user
from api.models import ChatMessage, ChatResponse
from core.database import get_db, User, ChatHistory
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
            actions_taken=result.get("actions_taken", [])
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