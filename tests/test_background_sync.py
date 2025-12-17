"""
Tests for background email sync service
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.background_sync import BackgroundEmailSync


class TestBackgroundEmailSync:
    """Tests for BackgroundEmailSync class"""

    def test_init_defaults(self):
        """Test default initialization values"""
        sync = BackgroundEmailSync()

        assert sync.sync_interval == 30  # Default from env
        assert sync.batch_size == 25  # Default from env
        assert sync.is_running == False
        assert sync._last_sync_results == {}

    @patch.dict(os.environ, {'SYNC_INTERVAL_SECONDS': '60', 'SYNC_BATCH_SIZE': '50'})
    def test_init_custom_env_values(self):
        """Test initialization with custom env values"""
        sync = BackgroundEmailSync()

        assert sync.sync_interval == 60
        assert sync.batch_size == 50

    def test_get_active_users_finds_recent_logins(self, db_session, test_user, inactive_user):
        """Test that only recently logged in users are returned"""
        sync = BackgroundEmailSync()

        # Patch SessionLocal to use our test session
        with patch('core.background_sync.SessionLocal', return_value=db_session):
            users = sync.get_active_users(db_session)

        # Should only find the active user (logged in within 24 hours)
        assert len(users) == 1
        assert users[0].id == test_user.id
        assert users[0].email == "test@example.com"

    def test_get_active_users_requires_oauth_token(self, db_session):
        """Test that users without oauth tokens are excluded"""
        from core.database import User

        # Create user without oauth token
        user_no_token = User(
            id="no-token-user",
            email="notoken@example.com",
            name="No Token User",
            provider="google",
            oauth_access_token=None,  # No token
            last_login=datetime.utcnow()
        )
        db_session.add(user_no_token)
        db_session.commit()

        sync = BackgroundEmailSync()
        users = sync.get_active_users(db_session)

        assert len(users) == 0

    def test_sync_user_emails_gmail(self, db_session, test_user, mock_gmail_service):
        """Test syncing emails for a Gmail user"""
        mock_emails = [
            MagicMock(is_urgent=False),
            MagicMock(is_urgent=True),
        ]
        mock_gmail_service.fetch_emails.return_value = {'emails': mock_emails}

        sync = BackgroundEmailSync()
        sync.gmail_service = mock_gmail_service

        result = sync.sync_user_emails(db_session, test_user)

        assert result['user_email'] == test_user.email
        assert result['provider'] == 'google'
        assert result['synced'] == 2
        assert result['urgent'] == 1
        assert result['errors'] == []

        mock_gmail_service.fetch_emails.assert_called_once()

    def test_sync_user_emails_microsoft(self, db_session, microsoft_user, mock_outlook_service):
        """Test syncing emails for a Microsoft user"""
        mock_emails = [
            MagicMock(is_urgent=True),
            MagicMock(is_urgent=True),
            MagicMock(is_urgent=False),
        ]
        mock_outlook_service.fetch_emails.return_value = {'emails': mock_emails}

        sync = BackgroundEmailSync()
        sync.outlook_service = mock_outlook_service

        result = sync.sync_user_emails(db_session, microsoft_user)

        assert result['user_email'] == microsoft_user.email
        assert result['provider'] == 'microsoft'
        assert result['synced'] == 3
        assert result['urgent'] == 2
        assert result['errors'] == []

        mock_outlook_service.fetch_emails.assert_called_once()

    def test_sync_user_emails_handles_errors(self, db_session, test_user, mock_gmail_service):
        """Test error handling during sync"""
        mock_gmail_service.fetch_emails.side_effect = Exception("API Error")

        sync = BackgroundEmailSync()
        sync.gmail_service = mock_gmail_service

        result = sync.sync_user_emails(db_session, test_user)

        assert result['synced'] == 0
        assert result['urgent'] == 0
        assert len(result['errors']) == 1
        assert "API Error" in result['errors'][0]

    def test_run_sync_cycle_no_users(self, db_session):
        """Test sync cycle with no active users"""
        sync = BackgroundEmailSync()

        with patch('core.background_sync.SessionLocal', return_value=db_session):
            result = sync.run_sync_cycle()

        assert result['users_synced'] == 0
        assert result['total_emails'] == 0
        assert result['total_urgent'] == 0
        assert 'timestamp' in result

    def test_run_sync_cycle_with_users(self, db_session, test_user, mock_gmail_service):
        """Test sync cycle processes all users"""
        mock_emails = [MagicMock(is_urgent=True)]
        mock_gmail_service.fetch_emails.return_value = {'emails': mock_emails}

        sync = BackgroundEmailSync()
        sync.gmail_service = mock_gmail_service

        with patch('core.background_sync.SessionLocal', return_value=db_session):
            result = sync.run_sync_cycle()

        assert result['users_synced'] == 1
        assert result['total_emails'] == 1
        assert result['total_urgent'] == 1

    def test_stop_sets_flag(self):
        """Test stop method sets is_running to False"""
        sync = BackgroundEmailSync()
        sync.is_running = True

        sync.stop()

        assert sync.is_running == False

    def test_get_last_sync_results(self):
        """Test retrieving last sync results"""
        sync = BackgroundEmailSync()
        sync._last_sync_results = {'test': 'data'}

        result = sync.get_last_sync_results()

        assert result == {'test': 'data'}

    @pytest.mark.asyncio
    async def test_start_background_loop_runs(self):
        """Test background loop starts and can be stopped"""
        sync = BackgroundEmailSync()
        sync.sync_interval = 1  # Fast for testing

        # Start the loop and stop it quickly
        loop_task = asyncio.create_task(sync.start_background_loop())

        # Wait for initial delay to pass
        await asyncio.sleep(0.1)

        assert sync.is_running == True

        # Stop the loop
        sync.stop()

        # Cancel the task
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

        assert sync.is_running == False


class TestBackgroundSyncIntegration:
    """Integration tests for background sync with database"""

    def test_full_sync_cycle(self, db_session, test_user, sample_emails, mock_gmail_service):
        """Test a full sync cycle with real database objects"""
        # Return fresh emails
        new_emails = [
            MagicMock(is_urgent=False),
            MagicMock(is_urgent=True),
        ]
        mock_gmail_service.fetch_emails.return_value = {'emails': new_emails}

        sync = BackgroundEmailSync()
        sync.gmail_service = mock_gmail_service

        with patch('core.background_sync.SessionLocal', return_value=db_session):
            result = sync.run_sync_cycle()

        # Verify sync completed
        assert result['users_synced'] == 1
        assert result['total_emails'] == 2
        assert result['total_urgent'] == 1
        assert result['errors'] == []

        # Verify last sync results updated
        assert sync.get_last_sync_results() == result

    def test_mixed_providers(self, db_session, test_user, microsoft_user, mock_gmail_service, mock_outlook_service):
        """Test sync with both Gmail and Microsoft users"""
        mock_gmail_service.fetch_emails.return_value = {
            'emails': [MagicMock(is_urgent=False)]
        }
        mock_outlook_service.fetch_emails.return_value = {
            'emails': [MagicMock(is_urgent=True), MagicMock(is_urgent=True)]
        }

        sync = BackgroundEmailSync()
        sync.gmail_service = mock_gmail_service
        sync.outlook_service = mock_outlook_service

        with patch('core.background_sync.SessionLocal', return_value=db_session):
            result = sync.run_sync_cycle()

        assert result['users_synced'] == 2
        assert result['total_emails'] == 3
        assert result['total_urgent'] == 2
