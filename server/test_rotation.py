import os
import time
import unittest
from unittest.mock import patch
from security import current_or_previous


class RotationTests(unittest.TestCase):
    def test_previous_requires_future_finite_deadline(self):
        base={'TEST_KEY':'new-secret','TEST_KEY_PREVIOUS':'old-secret'}
        for deadline in ['', 'invalid', '0', str(time.time()-1), 'inf', 'nan']:
            with patch.dict(os.environ,{**base,'TEST_KEY_PREVIOUS_UNTIL':deadline}):
                self.assertFalse(current_or_previous('old-secret','TEST_KEY'))
                self.assertTrue(current_or_previous('new-secret','TEST_KEY'))
        with patch.dict(os.environ,{**base,'TEST_KEY_PREVIOUS_UNTIL':str(time.time()+60)}):
            self.assertTrue(current_or_previous('old-secret','TEST_KEY'))
            self.assertFalse(current_or_previous('wrong','TEST_KEY'))

    def test_empty_credentials_are_never_valid(self):
        with patch.dict(os.environ,{'TEST_KEY':'','TEST_KEY_PREVIOUS':'','TEST_KEY_PREVIOUS_UNTIL':str(time.time()+60)}):
            self.assertFalse(current_or_previous('','TEST_KEY'))
