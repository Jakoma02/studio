from django.db import models
from kolibri_content import base_models
from kolibri_content.fields import JSONField
from kolibri_public.search import BitmaskFieldsMixin
from kolibri_public.search import BitmaskFieldsQueryset
from le_utils.constants.labels.accessibility_categories import (
    ACCESSIBILITYCATEGORIESLIST,
)
from le_utils.constants.labels.learning_activities import LEARNINGACTIVITIESLIST
from le_utils.constants.labels.levels import LEVELSLIST
from le_utils.constants.labels.needs import NEEDSLIST
from le_utils.constants.labels.subjects import SUBJECTSLIST
from mptt.managers import TreeManager
from mptt.querysets import TreeQuerySet

from contentcuration.models import Country
from contentcuration.models import Language


class ContentTag(base_models.ContentTag):
    pass


class ContentNodeQueryset(TreeQuerySet, BitmaskFieldsQueryset):
    pass


class ContentNodeManager(
    models.Manager.from_queryset(ContentNodeQueryset), TreeManager
):
    def get_queryset(self, *args, **kwargs):
        """
        Ensures that this manager always returns nodes in tree order.
        """
        return (
            super(TreeManager, self)
            .get_queryset(*args, **kwargs)
            .order_by(self.tree_id_attr, self.left_attr)
        )


class ContentNode(base_models.ContentNode, BitmaskFieldsMixin):
    bitmask_metadata_lookup = {
        "learning_activities": LEARNINGACTIVITIESLIST,
        "categories": SUBJECTSLIST,
        "grade_levels": LEVELSLIST,
        "accessibility_labels": ACCESSIBILITYCATEGORIESLIST,
        "learner_needs": NEEDSLIST,
    }

    lang = models.ForeignKey(Language, blank=True, null=True, on_delete=models.SET_NULL)

    # Fields used only on Kolibri and not imported from a content database
    # Total number of coach only resources for this node
    num_coach_contents = models.IntegerField(default=0, null=True, blank=True)
    # Total number of available resources on the device under this topic - if this is not a topic
    # then it is 1
    on_device_resources = models.IntegerField(default=0, null=True, blank=True)

    # Use this to annotate ancestor information directly onto the ContentNode, as it can be a
    # costly lookup
    # Don't use strict loading as the titles used to construct the ancestors can contain
    # control characters, which will fail strict loading.
    ancestors = JSONField(
        default=[], null=True, blank=True, load_kwargs={"strict": False}
    )

    objects = ContentNodeManager()


class File(base_models.File):
    lang = models.ForeignKey(Language, blank=True, null=True, on_delete=models.SET_NULL)


class LocalFile(base_models.LocalFile):
    pass


class AssessmentMetaData(base_models.AssessmentMetaData):
    pass


class ChannelMetadata(base_models.ChannelMetadata, BitmaskFieldsMixin):
    # Note: The `categories` field should contain a _list_, NOT a _dict_.

    bitmask_metadata_lookup = {
        "categories": SUBJECTSLIST,
    }

    # precalculated fields during annotation/migration
    published_size = models.BigIntegerField(default=0, null=True, blank=True)
    total_resource_count = models.IntegerField(default=0, null=True, blank=True)
    included_languages = models.ManyToManyField(
        Language, related_name="public_channels", verbose_name="languages", blank=True
    )
    order = models.PositiveIntegerField(default=0, null=True, blank=True)
    public = models.BooleanField()
    categories = models.JSONField(null=True, blank=True)
    countries = models.ManyToManyField(Country, related_name="public_channels")


class MPTTTreeIDManager(models.Model):
    """
    This is added as insurance against concurrency issues. It seems far less likely than for our
    regular channel tree_ids, but is here as a safety.

    Because MPTT uses plain integers for tree IDs and does not use an auto-incrementing field for them,
    the same ID can sometimes be assigned to two trees if two channel create ops happen concurrently.

    As we are using this table only for the ID generation, it does not need any fields.

    We resolve this by creating a dummy table and using its ID as the tree index to take advantage of the db's
    concurrency-friendly way of generating sequential integer IDs. There is a custom migration that ensures
    that the number of records (and thus id) matches the max tree ID number when this table gets added.
    """
