from django.test import TestCase
from django.contrib.auth import get_user_model

class UserTest(TestCase):
    def test_create_user(self):
        User = get_user_model()
        user = User.objects.create_user(username='testuser', password='testpass')
        self.assertEqual(user.username, 'testuser')
        self.assertTrue(user.check_password('testpass'))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)