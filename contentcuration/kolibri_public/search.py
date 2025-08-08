"""
Avoiding direct model imports in here so that we can import these functions into places
that should not initiate the Django app registry.

Modified from:
https://github.com/learningequality/kolibri/blob/0f6bb6781a4453cd9fdc836d52b65dd69e395b20/kolibri/core/content/utils/search.py

With model import references changed to either contentcuration or kolibri_public as appropriate
and any non-Postgres logic removed in favour of Postgres only.
"""
import hashlib

from django.contrib.postgres.aggregates import BitOr
from django.core.cache import cache
from django.db import models
from django.db.models import Case
from django.db.models import F
from django.db.models import Max
from django.db.models import Value
from django.db.models import When


class BitmaskFieldsQueryset(models.query.QuerySet):
    def has_all_labels(self, field_name, labels):
        """
        Returns a queryset that filters for nodes that have all the specified labels
        in the specified field.
        """
        bitmasks = self.model.metadata_bitmasks[field_name]
        bits = {}
        for label in labels:
            if label in bitmasks:
                bitmask_fieldname = bitmasks[label]["bitmask_field_name"]
                if bitmask_fieldname not in bits:
                    bits[bitmask_fieldname] = 0
                bits[bitmask_fieldname] += bitmasks[label]["bits"]

        filters = {}
        annotations = {}
        for bitmask_fieldname, bits in bits.items():
            annotation_fieldname = "{}_{}".format(bitmask_fieldname, "masked")
            filters[annotation_fieldname] = bits
            annotations[annotation_fieldname] = F(bitmask_fieldname).bitand(bits)

        return self.annotate(**annotations).filter(**filters)


class BitmaskFieldsMixin:
    def __init_subclass__(cls, **kwargs):
        if not hasattr(cls, "bitmask_metadata_lookup"):
            raise ValueError(
                "Subclasses of BitmaskFieldsMixin must define a 'bitmask_metadata_lookup' class attribute."
            )

        super().__init_subclass__(**kwargs)

        cls.metadata_bitmasks = {}
        cls.bitmask_fieldnames = {}
        cls._populate_bitmask_data()
        cls._create_bitmask_fields()

        cls.objects = models.Manager.from_queryset(BitmaskFieldsQueryset)

    @classmethod
    def _populate_bitmask_data(cls):
        for key, labels in cls.bitmask_metadata_lookup.items():
            bitmask_lookup = {}
            i = 0
            while (chunk := labels[i : i + 64]) :
                bitmask_field_name = "{}_bitmask_{}".format(key, i)
                cls.bitmask_fieldnames[bitmask_field_name] = []
                for j, label in enumerate(chunk):
                    info = {
                        "bitmask_field_name": bitmask_field_name,
                        "field_name": key,
                        "bits": 2 ** (64 * i + j),
                        "label": label,
                    }
                    bitmask_lookup[label] = info
                    cls.bitmask_fieldnames[bitmask_field_name].append(info)
                i += 64
            cls.metadata_bitmasks[key] = bitmask_lookup

    @classmethod
    def _create_bitmask_fields(cls):
        for bitmask_fieldname in cls.bitmask_fieldnames:
            field = models.BigIntegerField(default=0, null=True, blank=True)
            field.contribute_to_class(cls, bitmask_fieldname)


def _get_available_languages(base_queryset):
    # Updated to use contentcuration Language model
    from contentcuration.models import Language

    langs = Language.objects.filter(
        id__in=base_queryset.exclude(lang=None)
        .values_list("lang_id", flat=True)
        .distinct()
        # Updated to use contentcuration field names
        # Convert language objects to dicts mapped to the kolibri field names
    ).values("id", lang_name=F("native_name"))
    return list(langs)


def _get_available_channels(base_queryset):
    # Updated to use the kolibri_public ChannelMetadata model
    from kolibri_public.models import ChannelMetadata

    return list(
        ChannelMetadata.objects.filter(
            id__in=base_queryset.values_list("channel_id", flat=True).distinct()
        ).values("id", "name")
    )


# Remove the SQLite Bitwise OR definition as not needed.


def get_available_contentnode_metadata_labels(base_queryset):
    # Updated to use the kolibri_public ChannelMetadata model
    from kolibri_public.models import ChannelMetadata

    model = base_queryset.model

    content_cache_key = str(
        ChannelMetadata.objects.all().aggregate(updated=Max("last_updated"))["updated"]
    )
    cache_key = "search-labels:{}:{}".format(
        content_cache_key,
        hashlib.md5(str(base_queryset.query).encode("utf8")).hexdigest(),
    )
    if cache_key not in cache:
        base_queryset = base_queryset.order_by()
        aggregates = {}
        for field in model.bitmask_fieldnames:
            field_agg = field + "_agg"
            aggregates[field_agg] = BitOr(field)
        output = {}
        agg = base_queryset.aggregate(**aggregates)
        for field, values in model.bitmask_fieldnames.items():
            bit_value = agg[field + "_agg"]
            for value in values:
                if value["field_name"] not in output:
                    output[value["field_name"]] = []
                if bit_value is not None and bit_value & value["bits"]:
                    output[value["field_name"]].append(value["label"])
        output["languages"] = _get_available_languages(base_queryset)
        output["channels"] = _get_available_channels(base_queryset)
        cache.set(cache_key, output, timeout=None)
    return cache.get(cache_key)


def get_all_contentnode_label_metadata():
    # Updated to use the kolibri_public ContentNode model
    from kolibri_public.models import ContentNode

    return get_available_contentnode_metadata_labels(
        ContentNode.objects.filter(available=True)
    )


def annotate_label_bitmasks(queryset):
    model = queryset.model

    update_statements = {}
    for bitmask_fieldname, label_info in model.bitmask_fieldnames.items():
        update_statements[bitmask_fieldname] = sum(
            Case(
                When(
                    **{
                        info["field_name"] + "__contains": info["label"],
                        "then": Value(info["bits"]),
                    }
                ),
                default=Value(0),
            )
            for info in label_info
        )
    queryset.update(**update_statements)
