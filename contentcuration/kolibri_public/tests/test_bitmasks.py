from django.test import TestCase
from kolibri_public.models import ContentNode
from kolibri_public.tests.utils.mixer import KolibriPublicMixer


class ContentNodeBitmasksTestCase(TestCase):
    def setUp(self):
        super().setUp()
        mixer = KolibriPublicMixer()
        self.contentnode = mixer.blend(ContentNode)

    def test_has_bitmap_fields(self):
        expected_fields = [
            "learning_activities_bitmask_0",
            "categories_bitmask_0",
            "grade_levels_bitmask_0",
            "accessibility_labels_bitmask_0",
            "learner_needs_bitmask_0",
        ]
        print(self.contentnode.__dict__)
        for field in expected_fields:
            self.assertTrue(
                hasattr(self.contentnode, field), f"Field {field} not found"
            )
