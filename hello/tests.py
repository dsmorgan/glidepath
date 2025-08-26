from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    def test_home_returns_hello_world(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Hello, World!')
