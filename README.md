# SAIGBOX V3 - Complete Implementation Requirements

## Project Overview
Create a clean, production-ready version 3 of SAIGBOX that maintains all existing UI design and functionality while ensuring all features are fully implemented and working correctly. The system must be a complete, functional email management platform with an AI assistant (SAIG).

## Core Architecture Requirements

### 1. Technology Stack
- **Backend**: FastAPI (Python)
- **Frontend**: Single HTML file with embedded JavaScript (maintain current Tailwind CSS design)
- **Database**: SQLite with SQLAlchemy ORM
- **Email Sync**: Simple Gmail API integration only (no complex sync services)
- **AI Assistant**: AWS Bedrock Claude integration for SAIG
- **Authentication**: JWT tokens with OAuth 2.0 for Gmail

### 2. File Structure (Clean & Organized)
```
saigbox-v3/
├── api/
│   ├── main.py                 # Main FastAPI application
│   ├── auth.py                 # Authentication & JWT handling
│   ├── models.py               # Pydantic models for API
│   └── routes/
│       ├── emails.py           # Email CRUD operations
│       ├── actions.py          # Action items endpoints
│       ├── huddles.py          # Huddles management
│       ├── trash.py            # Trash operations
│       └── saig.py             # SAIG chat endpoints
├── core/
│   ├── database.py             # Database models & session
│   ├── gmail_service.py        # Gmail API integration
│   ├── saig_assistant.py       # SAIG AI logic
│   └── email_processor.py      # Email parsing & storage
├── static/
│   └── index.html              # Single-page application
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
└── README.md                   # Setup instructions
```

## Feature Requirements

### 1. Email Inbox (MUST BE FULLY FUNCTIONAL)
**Current Status**: Emails load but sync has issues
**Requirements**:
- Display emails in a clean list view with sender, subject, preview, and timestamp
- Real-time sync with Gmail (fetch new emails every 30 seconds)
- Mark as read/unread functionality
- Star/unstar emails
- Search emails by keyword
- Pagination (load more on scroll)
- Email detail view with full content
- Reply, forward, and compose new emails
- Move to trash functionality

**Implementation Notes**:
```python
# Simple Gmail sync - no complex sync services
class GmailService:
    def fetch_emails(self, max_results=50):
        # Direct Gmail API call
        # Store in database
        # Return formatted emails
    
    def mark_as_read(self, email_id):
        # Update Gmail and local database
    
    def move_to_trash(self, email_id):
        # Move in Gmail and update database
```

### 2. SAIG Chat Assistant (MAINTAIN EXISTING FUNCTIONALITY)
**Current Status**: Working
**Requirements**:
- Floating chat interface in bottom-right corner
- Context-aware responses about emails
- Ability to search emails via chat
- Compose emails through chat
- Summarize email threads
- Schedule meetings from emails
- Natural language email operations ("mark all emails from John as read")

**Key Features to Preserve**:
- Green gradient design (#0f766e to #059669)
- Smooth animations
- Message history
- Typing indicators
- Error handling with retry

### 3. Action Items (FULLY IMPLEMENT)
**Current Status**: UI exists but functionality incomplete
**Requirements**:
- Extract action items from emails automatically
- Manual action item creation
- Due dates and priorities
- Mark as complete/incomplete
- Filter by status (pending, completed, overdue)
- Link action items to source emails
- Reminder notifications

**Database Schema**:
```sql
CREATE TABLE action_items (
    id UUID PRIMARY KEY,
    email_id UUID REFERENCES emails(id),
    title TEXT NOT NULL,
    description TEXT,
    due_date DATETIME,
    priority INTEGER,
    status VARCHAR(20),
    created_at DATETIME,
    completed_at DATETIME
);
```

### 4. Trash Management (FULLY IMPLEMENT)
**Current Status**: Basic UI exists
**Requirements**:
- Move emails to trash (soft delete)
- View trash folder
- Restore emails from trash
- Permanently delete emails
- Empty trash functionality
- Auto-delete after 30 days

**Implementation**:
```python
class TrashService:
    def move_to_trash(self, email_id):
        # Set deleted_at timestamp
        # Update Gmail labels
    
    def restore_email(self, email_id):
        # Clear deleted_at
        # Restore Gmail labels
    
    def empty_trash(self):
        # Permanently delete all trashed items
```

### 5. Huddles (FULLY IMPLEMENT)
**Current Status**: UI exists but no backend
**Requirements**:
- Create huddles (group conversations)
- Add/remove participants
- Share emails within huddles
- Huddle chat/comments
- Notification system
- Archive huddles
- Search within huddles

**Database Schema**:
```sql
CREATE TABLE huddles (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    created_by UUID,
    created_at DATETIME,
    status VARCHAR(20)
);

CREATE TABLE huddle_members (
    huddle_id UUID,
    user_email VARCHAR(255),
    role VARCHAR(20)
);

CREATE TABLE huddle_messages (
    id UUID PRIMARY KEY,
    huddle_id UUID,
    sender_email VARCHAR(255),
    message TEXT,
    created_at DATETIME
);
```

## UI/UX Requirements

### 1. Maintain Current Design
- Dark sidebar with navigation
- Clean white content area
- Tailwind CSS styling
- Responsive layout
- Smooth transitions
- Loading states
- Error messages

### 2. Color Scheme
- Primary: Teal/Green gradient (#0f766e to #059669)
- Background: Gray-50 (#f9fafb)
- Text: Gray-900 (#111827)
- Borders: Gray-200 (#e5e7eb)

### 3. Navigation Structure
```
├── Inbox (default view)
├── Action Items
├── Huddles
├── Trash
└── SAIG Chat (floating)
```

## API Endpoints Required

### Email Endpoints
- `GET /api/emails` - List emails with pagination
- `GET /api/emails/{id}` - Get email details
- `PUT /api/emails/{id}/read` - Mark as read
- `PUT /api/emails/{id}/star` - Star/unstar
- `DELETE /api/emails/{id}` - Move to trash
- `POST /api/emails/compose` - Send new email
- `POST /api/emails/reply` - Reply to email
- `POST /api/emails/sync` - Trigger Gmail sync

### Action Items Endpoints
- `GET /api/actions` - List action items
- `POST /api/actions` - Create action item
- `PUT /api/actions/{id}` - Update action item
- `DELETE /api/actions/{id}` - Delete action item
- `POST /api/actions/extract` - Extract from email

### Huddles Endpoints
- `GET /api/huddles` - List huddles
- `POST /api/huddles` - Create huddle
- `GET /api/huddles/{id}` - Get huddle details
- `POST /api/huddles/{id}/members` - Add member
- `POST /api/huddles/{id}/messages` - Send message
- `POST /api/huddles/{id}/emails` - Share email

### Trash Endpoints
- `GET /api/trash` - List trashed items
- `POST /api/trash/{id}/restore` - Restore item
- `DELETE /api/trash/{id}` - Permanent delete
- `DELETE /api/trash/empty` - Empty all trash

### SAIG Endpoints
- `POST /api/saig/chat` - Send message to SAIG
- `GET /api/saig/history` - Get chat history
- `POST /api/saig/execute` - Execute SAIG command

## Critical Implementation Notes

### 1. Email Sync Strategy
```python
# Use simple polling approach - NO complex sync services
async def sync_emails():
    while True:
        try:
            # Fetch latest emails from Gmail
            new_emails = gmail_service.fetch_latest(since=last_sync_time)
            
            # Store in database
            for email in new_emails:
                db.store_email(email)
            
            # Notify connected clients via WebSocket
            await notify_clients(new_emails)
            
            # Wait 30 seconds
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Sync error: {e}")
            await asyncio.sleep(60)
```

### 2. Database Design Principles
- Use UUID for all IDs
- Soft deletes with deleted_at timestamp
- Proper indexes on frequently queried fields
- JSON fields for metadata
- Audit trails with created_at/updated_at

### 3. Error Handling
- All API endpoints must return consistent error responses
- Implement retry logic for external API calls
- Log all errors with context
- User-friendly error messages

### 4. Security Requirements
- JWT token validation on all protected endpoints
- Rate limiting on API endpoints
- Input validation and sanitization
- Secure storage of OAuth tokens
- CORS configuration for production

## Testing Requirements

### 1. Core Functionality Tests
- [ ] User can log in with Gmail OAuth
- [ ] Emails load and display correctly
- [ ] Email sync works continuously
- [ ] Mark as read/unread works
- [ ] Move to trash works
- [ ] Restore from trash works
- [ ] Action items can be created and completed
- [ ] Huddles can be created with members
- [ ] SAIG responds to queries
- [ ] Search functionality works

### 2. Performance Requirements
- Initial page load < 2 seconds
- Email list loads < 1 second
- SAIG response < 3 seconds
- Smooth scrolling with 1000+ emails

## Development Steps

### Phase 1: Core Setup (Day 1)
1. Create clean project structure
2. Set up FastAPI with all routes
3. Configure database models
4. Implement authentication

### Phase 2: Email Functionality (Day 2)
1. Gmail OAuth integration
2. Email fetching and storage
3. Email display and pagination
4. Read/unread/star functionality
5. Basic email operations

### Phase 3: SAIG Integration (Day 3)
1. Connect to AWS Bedrock
2. Implement chat interface
3. Add email context to SAIG
4. Test SAIG commands

### Phase 4: Features Implementation (Day 4)
1. Complete action items functionality
2. Implement trash management
3. Build huddles system
4. Add search functionality

### Phase 5: Polish & Testing (Day 5)
1. Fix all UI issues
2. Add loading states
3. Implement error handling
4. Performance optimization
5. Comprehensive testing

## Environment Variables Required
```env
# Gmail OAuth
GMAIL_CLIENT_ID=your_client_id
GMAIL_CLIENT_SECRET=your_client_secret
GMAIL_REDIRECT_URI=http://localhost:8000/auth/callback

# JWT
SECRET_KEY=your_secret_key
ALGORITHM=HS256

# AWS Bedrock (for SAIG)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1

# Database
DATABASE_URL=sqlite:///saigbox.db
```

## Success Criteria
1. **All features work without errors**
2. **Clean, maintainable code**
3. **No duplicate or conflicting sync services**
4. **Consistent UI/UX matching current design**
5. **Fast and responsive performance**
6. **Proper error handling throughout**
7. **Complete functionality for all advertised features**

## Additional Notes
- Focus on simplicity over complexity
- Use existing UI - do not redesign
- Ensure all features are actually functional, not just UI mockups
- Test with real Gmail account
- Document any limitations or known issues

---

**Priority**: The most critical requirement is that ALL features must be fully functional. No placeholder UI or "coming soon" features. Every button, every feature, every interaction must work as expected.