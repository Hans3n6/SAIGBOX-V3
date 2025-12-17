"""
Background email synchronization service
Fetches new emails for all active users periodically
Automatically extracts action items from urgent emails
"""
import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from core.database import SessionLocal, User, Email
from core.gmail_service import GmailService
from core.outlook_service import OutlookService
from core.action_extractor import action_extractor

logger = logging.getLogger(__name__)


class BackgroundEmailSync:
    """Background email synchronization service for all active users"""

    def __init__(self):
        self.gmail_service = GmailService()
        self.outlook_service = OutlookService()
        self.sync_interval = int(os.getenv('SYNC_INTERVAL_SECONDS', '30'))
        self.batch_size = int(os.getenv('SYNC_BATCH_SIZE', '25'))
        self.auto_extract_actions = os.getenv('AUTO_EXTRACT_ACTIONS', 'true').lower() == 'true'
        self.is_running = False
        self._last_sync_results: Dict[str, Any] = {}

    def get_active_users(self, db: Session) -> List[User]:
        """Get users with valid OAuth tokens who should be synced"""
        # Only sync users who have logged in within the last 24 hours
        # and have OAuth tokens
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        users = db.query(User).filter(
            User.oauth_access_token.isnot(None),
            User.last_login >= cutoff_time
        ).all()

        logger.info(f"Found {len(users)} active users for sync")
        return users

    async def sync_user_emails(self, db: Session, user: User) -> Dict[str, Any]:
        """Sync emails for a single user and extract action items from urgent emails"""
        result = {
            'user_email': user.email,
            'provider': user.provider or 'gmail',
            'synced': 0,
            'urgent': 0,
            'actions_created': 0,
            'errors': []
        }

        try:
            # Determine which service to use based on provider
            if user.provider == 'microsoft':
                logger.info(f"Syncing Outlook emails for {user.email}")
                sync_result = self.outlook_service.fetch_emails(
                    db, user, max_results=self.batch_size
                )
            else:
                # Default to Gmail
                logger.info(f"Syncing Gmail emails for {user.email}")
                sync_result = self.gmail_service.fetch_emails(
                    db, user, max_results=self.batch_size
                )

            # Count results
            emails = sync_result.get('emails', [])
            result['synced'] = len(emails)

            # Find urgent emails that haven't had actions extracted
            urgent_emails = [
                e for e in emails
                if getattr(e, 'is_urgent', False) and not getattr(e, 'auto_actions_created', False)
            ]
            result['urgent'] = len(urgent_emails)

            # Extract action items from urgent emails
            if self.auto_extract_actions and urgent_emails:
                logger.info(f"Extracting action items from {len(urgent_emails)} urgent emails for {user.email}")
                for email in urgent_emails:
                    try:
                        created_items = await action_extractor.create_action_items(db, email, user)
                        result['actions_created'] += len(created_items)

                        # Mark email as having actions created
                        email.auto_actions_created = True
                        email.action_count = len(created_items)
                        db.commit()
                    except Exception as e:
                        logger.error(f"Error extracting actions from email {email.id}: {e}")

            logger.info(
                f"Synced {result['synced']} emails for {user.email} "
                f"({result['urgent']} urgent, {result['actions_created']} actions created)"
            )

        except Exception as e:
            error_msg = f"Sync error for {user.email}: {str(e)}"
            logger.error(error_msg)
            result['errors'].append(error_msg)

        return result

    async def run_sync_cycle(self) -> Dict[str, Any]:
        """Run one complete sync cycle for all active users"""
        cycle_result = {
            'timestamp': datetime.utcnow().isoformat(),
            'users_synced': 0,
            'total_emails': 0,
            'total_urgent': 0,
            'total_actions': 0,
            'errors': []
        }

        db = SessionLocal()
        try:
            users = self.get_active_users(db)

            if not users:
                logger.info("No active users to sync")
                return cycle_result

            for user in users:
                try:
                    user_result = await self.sync_user_emails(db, user)
                    cycle_result['users_synced'] += 1
                    cycle_result['total_emails'] += user_result['synced']
                    cycle_result['total_urgent'] += user_result['urgent']
                    cycle_result['total_actions'] += user_result.get('actions_created', 0)
                    cycle_result['errors'].extend(user_result['errors'])
                except Exception as e:
                    logger.error(f"Error syncing user {user.email}: {e}")
                    cycle_result['errors'].append(str(e))

            logger.info(
                f"Sync cycle complete: {cycle_result['users_synced']} users, "
                f"{cycle_result['total_emails']} emails, "
                f"{cycle_result['total_urgent']} urgent, "
                f"{cycle_result['total_actions']} actions created"
            )

        except Exception as e:
            logger.error(f"Sync cycle error: {e}")
            cycle_result['errors'].append(str(e))
        finally:
            db.close()

        self._last_sync_results = cycle_result
        return cycle_result

    async def start_background_loop(self):
        """Main background sync loop - runs continuously"""
        logger.info(
            f"Starting background email sync service "
            f"(interval: {self.sync_interval}s, batch: {self.batch_size}, "
            f"auto_extract_actions: {self.auto_extract_actions})"
        )
        self.is_running = True

        # Initial delay to let the app fully start
        await asyncio.sleep(10)

        while self.is_running:
            try:
                # Run sync cycle (now async)
                await self.run_sync_cycle()
            except Exception as e:
                logger.error(f"Background sync error: {e}")

            # Wait for next sync interval
            await asyncio.sleep(self.sync_interval)

    def stop(self):
        """Stop the background sync"""
        logger.info("Stopping background email sync service")
        self.is_running = False

    def get_last_sync_results(self) -> Dict[str, Any]:
        """Get results from the last sync cycle"""
        return self._last_sync_results


# Global instance
background_sync = BackgroundEmailSync()
