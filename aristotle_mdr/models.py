from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_save,m2m_changed
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from model_utils.managers import InheritanceManager, InheritanceQuerySet
from model_utils.models import TimeStampedModel
from model_utils import Choices, FieldTracker
from notifications import notify
from django.dispatch import receiver

import datetime
from ckeditor.fields import RichTextField
from aristotle_mdr import perms
from aristotle_mdr.utils import url_slugify_concept, url_slugify_workgroup

import logging
logger = logging.getLogger(__name__)
logger.debug("Logging started for " + __name__)
# 11179 States
# When used these MUST be used as IntegerFields to allow status comparison
STATES = Choices (
           (0,'notprogressed',_('Not Progressed')),
           (1,'incomplete',_('Incomplete')),
           (2,'candidate',_('Candidate')),
           (3,'recorded',_('Recorded')),
           (4,'qualified',_('Qualified')),
           (5,'standard',_('Standard')),
           (6,'preferred',_('Preferred Standard')),
           (7,'superseded',_('Superseded')),
           (8,'retired',_('Retired')),
         )
VERY_RECENTLY_SECONDS = 15

class baseAristotleObject(TimeStampedModel):
    name = models.TextField(help_text=_("The primary name used for human identification purposes."))
    #TODO: Below needs to be changed to 'definition' but that change will break a lot of stuff. See also value_description
    # At the moment, this is just impacting the database and relations, as the UI uses the name of the field 'definition'
    description = RichTextField(_('definition'),help_text=_("Representation of a concept by a descriptive statement which serves to differentiate it from related concepts"))
    objects = InheritanceManager()

    class Meta:
        verbose_name = "item" # So the url_name works for items we can't determine
        #Can't be abstract as we need unique app wide IDs.
        abstract = True

    def was_modified_very_recently(self):
        return self.modified >= timezone.now() - datetime.timedelta(seconds=VERY_RECENTLY_SECONDS)

    def was_modified_recently(self):
        return self.modified >= timezone.now() - datetime.timedelta(days=1)
    was_modified_recently.admin_order_field = 'modified'
    was_modified_recently.boolean = True
    was_modified_recently.short_description = 'Modified recently?'

    def description_stub(self):
       from django.utils.html import strip_tags
       d = strip_tags(self.description)
       if len(d) > 150:
           d = d[0:150] + "..."
       return d

    def __str__(self):
        return "{name}".format(name = self.name)
    def __unicode__(self):
        return "{name}".format(name = self.name)

    # defined so we can access it during templates
    def get_verbose_name(self):
        return self._meta.verbose_name.title()
    def get_verbose_name_plural(self):
        return self._meta.verbose_name_plural.title()
    #@property
    #def url_name(self):
    #    s = self._meta.object_name
    #    s = s[0].lower() + s[1:]
    #    return s
    @property
    def url_name(self):
        return "item" # TODO: Changed as we've altered URL handling,but will refactor calls to this away later
    @property
    def help_name(self):
        return self._meta.model_name

    def can_edit(self,user):
        raise NotImplementedError #pragma: no cover -- This should always be overridden
    def can_view(self,user):
        raise NotImplementedError #pragma: no cover -- This should always be overridden

class unmanagedObject(baseAristotleObject):
    class Meta:
        abstract = True

    def can_edit(self,user):
        return user.is_superuser
    def can_view(self,user):
        return True

    @property
    def item(self):
        return self

class aristotleComponent(models.Model):
    class Meta:
        abstract = True
    def can_edit(self,user):
        return self.parentItem.can_edit(user)
    def can_view(self,user):
        return self.parentItem.can_view(user)


class registryGroup(unmanagedObject):
    managers   = models.ManyToManyField(User,blank=True,related_name="%(class)s_manager_in",verbose_name=_('Managers'))
    class Meta:
        abstract = True
    def can_edit(self,user):
        return user.is_superuser or self.managers.filter(pk=user.pk).exists()

"""
A registration authority is a proxy group that describes a governance process for "standardising" metadata.
"""
class RegistrationAuthority(registryGroup):
    template = "aristotle_mdr/registrationAuthority.html"
    locked_state = models.IntegerField(choices=STATES, default=STATES.candidate)
    public_state = models.IntegerField(choices=STATES, default=STATES.recorded)

    registrars = models.ManyToManyField(User,blank=True,related_name='registrar_in',verbose_name=_('Registrars'))

    # The below text fields allow for brief descriptions of the context of each
    # state for a particular Registration Authority
    # For example:
    # For a particular Registration Authority standard may mean"
    #   "Approved by a simple majority of the standing council of metadata standardisation"
    # While "Preferred Standard" may mean:
    #   "Approved by a two-thirds majority of the standing council of metadata standardisation"

    notprogressed = models.TextField(blank=True)
    incomplete = models.TextField(blank=True)
    candidate = models.TextField(blank=True)
    recorded = models.TextField(blank=True)
    qualified = models.TextField(blank=True)
    standard = models.TextField(blank=True)
    preferred = models.TextField(blank=True)
    superseded = models.TextField(blank=True)
    retired = models.TextField(blank=True)

    tracker=FieldTracker()

    class Meta:
        verbose_name_plural = _("Registration Authorities")

    def can_view(self,user):
        return True

    @property
    def unlocked_states(self):
        return range(STATES.notprogressed,self.locked_state)
    @property
    def locked_states(self):
        return range(self.locked_state,self.public_state)
    @property
    def public_states(self):
        return range(self.public_state,STATES.retired+1)

    def statusDescriptions(self):
        descriptions =[
            self.notprogressed,
            self.incomplete,
            self.candidate,
            self.recorded,
            self.qualified,
            self.standard,
            self.preferred,
            self.superseded,
            self.retired
        ]

        unlocked = [(STATES[i],descriptions[i]) for i in self.unlocked_states]
        locked = [(STATES[i],descriptions[i]) for i in self.locked_states]
        public = [(STATES[i],descriptions[i]) for i in self.public_states]

        return (('unlocked',unlocked),('locked',locked),('public',public))

    def register(self,item,state,user,registrationDate=timezone.now(),cascade=False,changeDetails=""):
        if not perms.user_can_change_status(user,item):
            # Should raise something here instead of quietly failing
            return None
        reg,created = Status.objects.get_or_create(
                concept=item,
                registrationAuthority=self,
                defaults ={
                    "registrationDate" : registrationDate,
                    "state" : state,
                    "changeDetails":changeDetails
                    }
                )
        if not created:
            reg.changeDetails = changeDetails
            reg.state = state
            reg.registrationDate = registrationDate
            reg.save()
        if cascade:
            for i in item.registry_cascade_items:
                if i is not None and perms.user_can_change_status(user,i):
                   self.register(i,state,user,registrationDate=registrationDate,cascade=cascade,changeDetails=changeDetails)
        return reg
    def giveRoleToUser(self,role,user):
        if role == 'registrar':
            self.registrars.add(user)
        if role == "manager":
            self.managers.add(user)
    def removeRoleFromUser(self,role,user):
        if role == 'registrar':
            self.registrars.remove(user)
        if role == "manager":
            self.managers.remove(user)

@receiver(post_save,sender=RegistrationAuthority)
def update_registration_authority_states(sender, instance, created, **kwargs):
    if not created:
        if instance.tracker.has_changed('public_state') or instance.tracker.has_changed('locked_state'):
            message = ("Registration '{ra}' changed its public or locked status level, "
                        "items registered by this authority may have stale visiblity states "
                        "and need to be manually updated."
                        ).format(ra = instance.name)
            logger.critical(message)

WORKGROUP_OWNERSHIP = Choices (
           (0,'registry',_('Registry')),
           (1,'authority',_('Registration Authorities')),
         )

class Workgroup(registryGroup):
    """
    A workgroup is a collection of associated users given control to work on a specific piece of work.
    Usually this work will be a specific collection or subset of objects, such as data elements or indicators, for a specific topic.

    Workgroup owners may choose to 'archive' a workgroup. All content remains visible,
    but the workgroup is hidden in lists.
    """
    template = "aristotle_mdr/workgroup.html"
    ownership = models.IntegerField(
        choices=WORKGROUP_OWNERSHIP, default=WORKGROUP_OWNERSHIP.authority,
        help_text=_("Specifies the 'owner' of the content of the workgroup. Selecting 'registry' allows any registration authority to progress and make items public, 'Registration authorities' specifies that only registration authorities associated with this workgroup may control their visibility.")
        )
    archived = models.BooleanField(default=False,
            help_text=_("Archived workgroups can no longer have new items or discussions created within them."),
            verbose_name=_('Archived'),
        )
    registrationAuthorities = models.ManyToManyField(
            RegistrationAuthority, blank=True, null=True,
            related_name="workgroups",
            verbose_name=_('Registration Authorities'),
            )

    viewers    = models.ManyToManyField(User,blank=True,related_name='viewer_in',verbose_name=_('Viewers'))
    submitters = models.ManyToManyField(User,blank=True,related_name='submitter_in',verbose_name=_('Submitters'))
    stewards   = models.ManyToManyField(User,blank=True,related_name='steward_in',verbose_name=_('Stewards'))

    roles = {'submitter':_("Submitter"),
            'viewer'    :_("Viewer"),
            'steward'   :_("Steward"),
            'manager'   :_("Manager")}

    tracker=FieldTracker()

    def get_absolute_url(self):
        return url_slugify_workgroup(self)

    @property
    def members(self):
        return self.viewers.all() | self.submitters.all() | self.stewards.all() | self.managers.all()

    def can_view(self,user):
        return self.members.filter(pk=user.pk).exists()

    @property
    def classedItems(self):
        # Convenience class as we can't call functions in templates
        return self.items.select_subclasses()

    def giveRoleToUser(self,role,user):
        if role == "manager":
            self.managers.add(user)
        if role == "viewer":
            self.viewers.add(user)
        if role == "submitter":
            self.submitters.add(user)
        if role == "steward":
            self.stewards.add(user)
        self.save()

    def removeRoleFromUser(self,role,user):
        if role == "manager":
            self.managers.remove(user)
        if role == "viewer":
            self.viewers.remove(user)
        if role == "submitter":
            self.submitters.remove(user)
        if role == "steward":
            self.stewards.remove(user)
        self.save()

    def removeUser(self,user):
        self.viewers.remove(user)
        self.submitters.remove(user)
        self.stewards.remove(user)
        self.managers.remove(user)

@receiver(post_save,sender=Workgroup)
def update_ownership(sender, instance, created, **kwargs):
    # only log if its an edit, not a newly created workgroup
    if not created and instance.tracker.has_changed('ownership'):
        message = ("Workgroup '{wg}' changed ownership, "
                    "cached public states for items in this workgroup are now "
                    "stale and need to be manually updated."
                    ).format(wg = instance.name)
        logger.critical(message)
# This would be like the below, but again, a better solution is needed.

def update_registation_authorities(sender, instance, action, **kwargs):
    # this will be slow, but necessary... perhaps this will encourage people to not
    # change or add registration authorities to workgroups willy-nilly.
    if action in ['post_add','post_remove','post_clear']:
        created = instance.created >= timezone.now() - datetime.timedelta(seconds=VERY_RECENTLY_SECONDS)
        # Dont fire this off if the object was created very recently within about the last 15 seconds.
        if not created:
            message = ("Workgroup '{wg}' has altered registration authorities, "
                        "cached public states for items in this workgroup are now "
                        "stale and need to be manually updated."
                        ).format(wg = instance.name)
            logger.critical(message)
    # In practice it seems the below is far too slow, so a better alternative is needed.
    #    for item in instance.items.all():
    #        item.recache_states()
m2m_changed.connect(update_registation_authorities, sender=Workgroup.registrationAuthorities.through)

class discussionAbstract(TimeStampedModel):
    body = models.TextField()
    author = models.ForeignKey(User)
    class Meta:
        abstract = True
    @property
    def edited(self):
        return self.created != self.modified

class DiscussionPost(discussionAbstract):
    workgroup = models.ForeignKey(Workgroup,related_name='discussions')
    title = models.CharField(max_length=256)
    relatedItems = models.ManyToManyField('_concept',blank=True,
                    related_name='relatedDiscussions',
                    )
    closed = models.BooleanField(default=False)
    class Meta:
        ordering = ['-modified']

    @property
    def active(self):
        return not self.closed

class DiscussionComment(discussionAbstract):
    post = models.ForeignKey(DiscussionPost, related_name='comments')
    class Meta:
        ordering = ['-created']


#class ReferenceDocument(models.Model):
#    url = models.URLField()
#    description = models.TextField()
#    object = models.ForeignKey(managedObject)

class ConceptQuerySet(InheritanceQuerySet):
    def visible(self,user):
        """
        Returns a queryset that returns all items that the given user has permission to view.
        For speed reasons and django queryset limitations , *doesn't* use `perms.user_can_view`
        however, is guaranteed to follow the same logic.

        It is **chainable** with other querysets. For example, both of these will work and return the same list::

            ObjectClass.objects.filter(name__contains="Person").visible()
            ObjectClass.objects.visible().filter(name__contains="Person")
        """
        if user.is_superuser:
            return self.all()
        if user.is_anonymous():
            return self.public()
        q = Q(_is_public=True)
        if user.profile.workgroups:
            # User can see everything in their workgroups.
            q |= Q(workgroup__in=user.profile.workgroups)
            # q |= Q(workgroup__user__profile=user)
        if user.profile.is_registrar:
            # User can see everything that is "readyToReview" or registered in their workgroup
            q |= Q(workgroup__registrationAuthorities__in=user.profile.registrarAuthorities.all(),readyToReview=True)
            q |= Q(workgroup__registrationAuthorities__in=user.profile.registrarAuthorities.all(),
                    statuses__registrationAuthority__in=user.profile.registrarAuthorities.all())
        return self.filter(q)
    def editable(self,user):
        """
        Returns a queryset that returns all items that the given user has permission to edit.
        For speed reasons and django queryset limitations , *doesn't* use `perms.user_can_edit`
        however, is guaranteed to follow the same logic.

        It is **chainable** with other querysets. For example, both of these will work and return the same list::

            ObjectClass.objects.filter(name__contains="Person").editable()
            ObjectClass.objects.editable().filter(name__contains="Person")
        """
        if user.is_superuser:
            return self.all()
        if user.is_anonymous():
            return self.none()
        q = Q()
        if user.submitter_in.exists() or user.steward_in.exists():
            if user.submitter_in.exists():
                q |= Q(_is_locked=False,workgroup__in=user.submitter_in.all())
            if user.steward_in.exists():
                q |= Q(workgroup__in=user.steward_in.all())
            return self.filter(q)
        else:
            return self.none()
    def public(self):
        """
        Returns a list of public items from the queryset.

        This is a chainable query set, that filters on items which have the internal
        `_is_public` flag set to true.

        Both of these examples will work and return the same list::

            ObjectClass.objects.filter(name__contains="Person").public()
            ObjectClass.objects.public().filter(name__contains="Person")
        """
        return self.filter(_is_public=True)

class ConceptManager(InheritanceManager):
    """The ``ConceptManager`` is the default object manager for ``concept`` and
    ``_concept`` items, and extends from the django-model-utils ``InheritanceManager``.

    It provides access to the ``ConceptQuerySet`` to allow for easy permissions-based
    filtering of ISO 11179 Concept-based items.
    """
    def get_query_set(self):
        return ConceptQuerySet(self.model)
    def get_queryset(self):
        return ConceptQuerySet(self.model)
    def __getattr__(self, attr, *args):
        # Only let the slow ones through to the queryset
        if attr in ['editable','visible','public']:
            return getattr(self.get_queryset(), attr, *args)
        else:
            return getattr(self.__class__, attr, *args)

class _concept(baseAristotleObject):
    """
    This is the base concrete class that ``Status`` items attach to, and to which
    collection objects refer to. It is not marked abstract in the Django Meta class, and
    **must not be inherited from**. It has relatively few fields and is a convenience
    class to link with in relationships.
    """
    objects = ConceptManager()
    template = "aristotle_mdr/concepts/managedContent.html"
    readyToReview = models.BooleanField(default=False)
    workgroup = models.ForeignKey(Workgroup,related_name="items")
    # We will query on these, so want them cached with the items themselves
    # To be usable these must be updated when statuses are changed
    _is_public =  models.BooleanField(default=False)
    _is_locked =  models.BooleanField(default=False)

    class Meta:
        verbose_name = "item" # So the url_name works for items we can't determine

    def can_edit(self,user):
        if self.is_public():
            return self.workgroup.stewards.filter(pk=user.pk).exists()
        elif self.is_locked():
            return self.workgroup.stewards.filter(pk=user.pk).exists()
        elif self.is_registered:
            return self.workgroup.submitters.filter(pk=user.pk).exists() \
                or self.workgroup.stewards.filter(pk=user.pk).exists()
        else:
            return self.workgroup.submitters.filter(pk=user.pk).exists() or self.workgroup.stewards.filter(pk=user.pk).exists()

    def can_view(self,user):
        if self.is_public():
            return True
        elif user.is_anonymous():
            return False
        # If the user can view objects in this workgroup
        if self.workgroup.members.filter(pk=user.pk).exists():
            return True
        # if the item is registered and the user is a registrar view view permissions in that authority.
        if self.is_registered:
            for s in self.statuses.all():
                ra = s.registrationAuthority
                if ra.registrars.filter(pk=user.pk).exists():
                    return True
        if self.readyToReview:
            for ra in self.workgroup.registrationAuthorities.all():
                if ra.registrars.filter(pk=user.pk).exists():
                    return True
        return False


    @property
    def item(self):
        """
        Performs a lookup using ``model_utils.managers.InheritanceManager`` to find the
        subclassed item
        """
        return _concept.objects.get_subclass(pk=self.pk)

    def relatedItems(self,user=None):
        return []

    @classmethod
    def get_autocomplete_name(self):
        return 'Autocomplete'+"".join(self._meta.verbose_name.title().split())
    @staticmethod
    def autocomplete_search_fields(self):
        return ("name__icontains",)
    def get_absolute_url(self):
        return url_slugify_concept(self)

    @property
    def registry_cascade_items(self):
        """
        This returns the items that can be registered along with the this item.
        If a subclass of _concept (eg. X) defines this method, then when an item
        of class X is registered with `cascade=True` then that item, and item
        with returned by this method will all recieve the same registration.
        Reimplementations of this MUST return lists
        """
        return []

    @property
    def is_registered(self):
        return self.statuses.count() > 0

    @property
    def is_superseded(self):
        return all(STATES.superseded == status.state for status in self.statuses.all()) and self.superseded_by

    @property
    def is_retired(self):
        return all(STATES.retired == status.state for status in self.statuses.all())and self.statuses.count() > 0

    def check_is_public(self):
        """
            A concept is public if any registration authority that a Registration Authority of the workgroup
            has advanced it to a public state in that RA.
        """
        if self.workgroup.ownership == WORKGROUP_OWNERSHIP.authority:
            statuses = self.statuses.filter(registrationAuthority__in=self.workgroup.registrationAuthorities.all())
        elif  self.workgroup.ownership == WORKGROUP_OWNERSHIP.registry:
            statuses = self.statuses.all()
        return True in [s.state >= s.registrationAuthority.public_state for s in statuses]

    def is_public(self):
        return self._is_public
    is_public.boolean = True
    is_public.short_description = 'Public'

    def check_is_locked(self):
        """
            A concept is locked if any registration authority that a Registration Authority of the workgroup
            has advanced it to a locked state in that RA.
        """
        if self.workgroup.ownership == WORKGROUP_OWNERSHIP.authority:
            statuses = self.statuses.filter(registrationAuthority__in=self.workgroup.registrationAuthorities.all())
        elif  self.workgroup.ownership == WORKGROUP_OWNERSHIP.registry:
            statuses = self.statuses.all()
        return True in [s.state >= s.registrationAuthority.locked_state for s in statuses]

    def is_locked(self):
        return self._is_locked

    is_locked.boolean = True
    is_locked.short_description = 'Locked'

    def recache_states(self):
        self._is_public = self.check_is_public()
        self._is_locked = self.check_is_locked()
        self.save()

class concept(_concept):
    """
    This is an abstract class that all items that should behave like a 11179 Concept
    **must inherit from**. This model includes the definitions for many long and optional text
    fields and the self-referential ``superseded_by`` field. It is not possible to include this
    model in a ``ForeignKey`` or ``ManyToManyField``.
    """
    short_name = models.CharField(max_length=100,blank=True)
    version = models.CharField(max_length=20,blank=True)
    synonyms = models.CharField(max_length=200, blank=True)
    references = RichTextField(blank=True)
    origin_URI = models.URLField(blank=True,help_text="If imported, the original location of the item")
    comments = RichTextField(help_text="Descriptive comments about the metadata item.", blank=True)
    submitting_organisation = models.CharField(max_length=256, blank=True)
    responsible_organisation = models.CharField(max_length=256, blank=True)

    superseded_by = models.ForeignKey('self', related_name='supersedes',blank=True,null=True)

    objects = ConceptManager()

    class Meta:
        abstract = True

    @property
    def item(self):
        """
        Return self, because we already have the correct item.
        """
        return self

    @property
    def getPdfItems(self):
        return {}

class Status(TimeStampedModel):
    concept = models.ForeignKey(_concept,related_name="statuses")
    registrationAuthority = models.ForeignKey(RegistrationAuthority)
    changeDetails = models.CharField(max_length=512,blank=True,null=True)
    state = models.IntegerField(choices=STATES, default=STATES.incomplete)

    inDictionary = models.BooleanField(default=True)
    registrationDate = models.DateField()
    tracker=FieldTracker()

    class Meta:
        unique_together = ('concept', 'registrationAuthority',)
        verbose_name_plural = "Statuses"

    def unique_error_message(self, model_class, unique_check):
        if model_class == type(self) and unique_check == ('concept', 'registrationAuthority',):
            return _('This Object %(obj)s already has a status in Registration Authority "%(ra)s". Please update the exisiting status field instead of creating a new one.')%\
                    {'obj': self.concept,
                      'ra': self.registrationAuthority.name
                    }
        else:
            return super(Status, self).unique_error_message(model_class, unique_check)

    @property
    def state_name(self):
        return STATES[self.state]

    def __unicode__(self):
        return "{obj} is {stat} for {ra}".format(
                obj = self.concept.name,
                stat=self.state_name,
                ra=self.registrationAuthority
            )

class ObjectClass(concept):
    template = "aristotle_mdr/concepts/objectClass.html"

    class Meta:
        verbose_name_plural = "Object Classes"

class Property(concept):
    template = "aristotle_mdr/concepts/property.html"
    class Meta:
        verbose_name_plural = "Properties"

class Measure(unmanagedObject):
    pass
class UnitOfMeasure(concept):
    class Meta:
        verbose_name_plural = "Units Of Measure"

    template="aristotle_mdr/concepts/unitOfMeasure.html"
    measure = models.ForeignKey(Measure, blank=True, null=True)
    symbol =  models.CharField(max_length=20,blank=True)

class DataType(concept):
    template = "aristotle_mdr/concepts/dataType.html"

class ConceptualDomain(concept):
    """
    Implementation note: Since a Conceptual domain "must be either one or
    both an Enumerated Conceptual or a Described_Conceptual_Domain" there is
    no reason to model them separately.
    """

    template = "aristotle_mdr/concepts/conceptualDomain.html"
    #TODO: This needs to be changed to just 'description'
    value_description = models.TextField(_('description'),blank=True,
            help_text='Description or specification of a rule, reference, or range for a set of all value meanings for a Conceptual Domain')

class ValueMeaning(aristotleComponent):
    class Meta:
        ordering = ['order']
    meaning = models.CharField(max_length=255)
    conceptual_domain = models.ForeignKey(ConceptualDomain)
    order = models.PositiveSmallIntegerField("Position")
    start_date = models.DateField(blank=True,null=True,
            help_text='Date at which the value meaning became valid')
    end_date = models.DateField(blank=True,null=True,
            help_text='Date at which the value meaning ceased to be valid')
    def __unicode__(self):
        return "%s: %s - %s"%(self.conceptual_domain.name,self.value,self.meaning)

    @property
    def parentItem(self):
        return self.conceptual_domain


class ValueDomain(concept):
    """
    Implementation note: Since a Value domain "must be either one or
    both an Enumerated Valued or a Described_Value_Domain" there is
    no reason to model them separately.
    """

    template = "aristotle_mdr/concepts/valueDomain.html"

    data_type = models.ForeignKey(DataType,blank=True,null=True)
    format = models.CharField(max_length=100,blank=True,null=True)
    maximum_length = models.PositiveIntegerField(blank=True,null=True)
    unit_of_measure = models.ForeignKey(UnitOfMeasure,blank=True,null=True)

    conceptual_domain = models.ForeignKey(ConceptualDomain,blank=True,null=True)
    #TODO: This needs to be changed to just 'description'
    value_description = models.TextField(_('description'),blank=True,
            help_text='Description or specification of a rule, reference, or range for a set of all values for a Value Domain')
    #Below is a dirty, dirty hack that came from re-designing permissible values
    # TODO: Fix references to permissible and supplementary values
    @property
    def permissibleValues(self):
        return self.permissiblevalue_set.all()
    @property
    def supplementaryValues(self):
        return self.supplementaryvalue_set.all()

class AbstractValue(aristotleComponent):
    """
    Implementation note: Not the best name, but there will be times to
    subclass a "value" when its not just a permissible value.
    """

    class Meta:
        abstract = True
        ordering = ['order']
    value = models.CharField(max_length=32)
    meaning = models.CharField(max_length=255)
    value_meaning = models.ForeignKey(ValueMeaning, blank=True, null=True)
    valueDomain = models.ForeignKey(ValueDomain)
    order = models.PositiveSmallIntegerField("Position")
    start_date = models.DateField(blank=True,null=True,
            help_text='Date at which the value became valid')
    end_date = models.DateField(blank=True,null=True,
            help_text='Date at which the value ceased to be valid')
    def __unicode__(self):
        return "%s: %s - %s"%(self.valueDomain.name,self.value,self.meaning)

    @property
    def parentItem(self):
        return self.value_domain

class PermissibleValue(AbstractValue):
    pass
class SupplementaryValue(AbstractValue):
    pass



class DataElementConcept(concept):
    property_ = property #redefine in this context as we need 'property' for the 11179 terminology
    template = "aristotle_mdr/concepts/dataElementConcept.html"
    objectClass = models.ForeignKey(ObjectClass,blank=True,null=True)
    property = models.ForeignKey(Property,blank=True,null=True)
    conceptualDomain = models.ForeignKey(ConceptualDomain,blank=True,null=True)

    @property_
    def registry_cascade_items(self):
        return [self.objectClass,self.property]

# Yes this name looks bad - blame 11179:3:2013 for renaming "administered item" to "concept"
class DataElement(concept):
    template = "aristotle_mdr/concepts/dataElement.html"
    dataElementConcept = models.ForeignKey(DataElementConcept,verbose_name = "Data Element Concept",blank=True,null=True)
    valueDomain = models.ForeignKey(ValueDomain,verbose_name = "Value Domain",blank=True,null=True)

    @property
    def registry_cascade_items(self):
        return [self.dataElementConcept,self.valueDomain]


class DataElementDerivation(concept):
    derives = models.ForeignKey(DataElement,related_name="derived_from",
                blank=True,null=True)
    inputs = models.ManyToManyField(DataElement,
                related_name="input_to_derivation",
                blank=True,null=True)
    derivation_rule = models.TextField(blank=True)


class Package(concept):
    items = models.ManyToManyField(_concept,related_name="packages",blank=True,null=True)
    template = "aristotle_mdr/concepts/package.html"

    @property
    def classedItems(self):
        return self.items.select_subclasses()

# Create a 1-1 user profile so we don't need to extend user
# Thanks to http://stackoverflow.com/a/965883/764357
class PossumProfile(models.Model):
    user = models.OneToOneField(User, related_name='profile')
    savedActiveWorkgroup = models.ForeignKey(Workgroup,blank=True,null=True)
    favourites = models.ManyToManyField(_concept,related_name='favourited_by',blank=True)

    # Override save for inline creation of objects.
    # http://stackoverflow.com/questions/2813189/django-userprofile-with-unique-foreign-key-in-django-admin
    def save(self, *args, **kwargs):
        try:
            existing = PossumProfile.objects.get(user=self.user)
            self.id = existing.id #force update instead of insert
        except PossumProfile.DoesNotExist: #pragma: no cover
            pass
        models.Model.save(self, *args, **kwargs)

    @property
    def activeWorkgroup(self):
        return self.savedActiveWorkgroup or self.workgroups.first() or self.myWorkgroups.first()

    @property
    def workgroups(self):
        if self.user.is_superuser:
            return Workgroup.objects.all()
        else:
            return (self.user.viewer_in.all()    |\
                    self.user.submitter_in.all() |\
                    self.user.steward_in.all()   |\
                    self.user.workgroup_manager_in.all()).distinct()

    @property
    def myWorkgroups(self):
        return self.workgroups.filter(archived=False)

    @property
    def is_registrar(self):
        return perms.user_is_registrar(self.user)

    @property
    def discussions(self):
        return DiscussionPost.objects.filter(workgroup__in=self.myWorkgroups.all())

    @property
    def registrarAuthorities(self):
        """NOTE: This is a list of Authorities the user is a *registrar* in!."""
        if self.user.is_superuser:
                return RegistrationAuthority.objects.all()
        else:
            return self.user.registrar_in.all()

    def is_workgroup_manager(self,wg):
        return perms.user_is_workgroup_manager(self.user,wg)

    def is_favourite(self,item):
        return self.favourites.filter(pk=item.pk).exists()

    def toggleFavourite(self, item):
        if self.is_favourite(item):
            self.favourites.remove(item)
        else:
            self.favourites.add(item)

def create_user_profile(sender, instance, created, **kwargs):
    if created:
       profile, created = PossumProfile.objects.get_or_create(user=instance)
post_save.connect(create_user_profile, sender=User)

def recache_concept_states(sender, instance, created, **kwargs):
    instance.concept.recache_states()
post_save.connect(recache_concept_states, sender=Status)


#"""
#A collection is a user specified sharable collections of content.
#Collection owners can add and remove other owners, editors and viewers
#                  and add or remove content from the collection
#           viewers can see content in the collection
#In all cases, people can only see or add content they have permission to view in the wider registry.
#"""
#class Collection(models.Model):
#    items = models.ManyToManyField(_concept,related_name='in_collections')
#    owner = models.ManyToManyField(User, related_name='owned_collections')
#    viewer = models.ManyToManyField(User, related_name='subscribed_collections')

def defaultData():
    system = User.objects.get(username="aristotle")
    iso ,c = RegistrationAuthority.objects.get_or_create(
                name="ISO/IEC",description="ISO/IEC")
    iso_wg,c = Workgroup.objects.get_or_create(name="ISO/IEC Workgroup")
    iso_package,c = Package.objects.get_or_create(
        name="ISO/IEC 11404 DataTypes",
        description="A collection of datatypes as described in the ISO/IEC 11404 Datatypes standard",
        workgroup=iso_wg)
    iso.register(iso_package,STATES.standard,system,timezone.now())
    dataTypes = [
       ("Boolean","A binary value expressed using a string (e.g. true or false)."),
       ("Currency","A numeric value expressed using a particular medium of exchange."),
       ("Date/Time","A specific instance of time expressed in numeric form."),
       ("Number","A sequence of numeric characters which may contain decimals, excluding codes with 'leading' characters e.g. '01','02','03'. "),
       ("String","A sequence of alphabetic and/or numeric characters, including 'leading' characters e.g. '01','02','03'."),
       ]
    print("making datatypes:  ",end="")
    for name,desc in dataTypes:
        dt,created = DataType.objects.get_or_create(name=name,description=desc,workgroup=iso_wg)
        iso.register(dt,STATES.standard,system,datetime.date(2000,1,1))
        iso_package.items.add(dt)
        print("{name} ".format(name=name),end="")
    print("")

    sys_wg,c = Workgroup.objects.get_or_create(name="System Workgroup")
    unitsOfMeasure = [
        ("Length", [
         ("Centimetre", "cm"),
         ("Millimetre", "mm"),
        ]),
        ("Temperature", [
         ("Degree", "Celsius"),
        ]),
        ("Time", [
         ("Second", "s"),
         ("Minute", "min"),
         ("Hour", "h"),
         ("Day", "D"),
         ("Year", "Y"),
        ]),
        ("Weight", [
         ("Gram", "g"),
         ("Kilogram", "Kg"),
        ]),
    ]
    for measure,units in unitsOfMeasure:
        m,created = Measure.objects.get_or_create(name=measure,description="")
        print("making measure: {name}".format(name=measure),end="")
        print("  : units of measure:  ",end="")
        for name,symbol in units:
            u,created = UnitOfMeasure.objects.get_or_create(name=name,symbol=symbol,measure=m,workgroup=sys_wg)
            print("{name}".format(name=name),end="")
        print("")

def favourite_updated(recipient,obj):
    notify.send(obj, recipient=recipient, verb="changed a favourited item",
                comment=_('A favourite item (%(item)s) has been changed.') % {'item': obj})
def workgroup_item_updated(recipient,obj):
    notify.send(obj, recipient=recipient, verb="motified item in workgroup", target=obj.workgroup,
                comment=_('An item (%(item)s) has been updated in the workgroup "%(workgroup)s"') % {'item':obj, 'workgroup': obj.workgroup})
def workgroup_item_new(recipient,obj):
    notify.send(obj, recipient=recipient, verb="new item in workgroup", target=obj.workgroup,
                comment=_('An new item (%(item)s) is in the workgroup "%(workgroup)s"') % {'item':obj, 'workgroup': obj.workgroup})

@receiver(post_save)
def concept_saved(sender, instance, created, **kwargs):
    if not issubclass(sender, _concept):
        return
    if kwargs.get('raw'):
        # Don't run during loaddata
        return
    for p in instance.favourited_by.all():
        favourite_updated(recipient=p.user,obj=instance)
    for user in instance.workgroup.viewers.all():
        if created:
            workgroup_item_new(recipient=user,obj=instance)
        else:
            workgroup_item_updated(recipient=user,obj=instance)
    try:
        # This will fail during first load, and if admins delete aristotle.
        system = User.objects.get(username="aristotle")
        for post in instance.relatedDiscussions.all():
            DiscussionComment.objects.create(
                post = post,
                body = 'The item "{name}" (id:{iid}) has been changed.\n\n\
                    <a href="{url}">View it on the main site.</a>.'.format(
                    name=instance.name,
                    iid = instance.id,
                    url = reverse("aristotle:item",args=[instance.id])
                ),
                author = system,
            )
    except:
        pass
@receiver(post_save,sender=DiscussionComment)
def new_comment_created(sender, **kwargs):
    comment = kwargs['instance']
    post = comment.post
    if kwargs.get('raw'):
        # Don't run during loaddata
        return
    if not kwargs['created']:
        return # We don't need to notify a topic poster of an edit.
    if comment.author == post.author:
        return # We don't need to tell someone they replied to themselves
    notify.send(comment.author, recipient=post.author, verb="comment on post", target=post,
                comment=_('%(commenter)s) commented on the post "%(post)s"') % {'commenter':comment.author, 'post':post.title})

@receiver(post_save,sender=DiscussionPost)
def new_post_created(sender, **kwargs):
    post = kwargs['instance']
    if kwargs.get('raw'):
        # Don't run during loaddata
        return
    if not kwargs['created']:
        return # We don't need to notify a topic poster of an edit.
    for user in post.workgroup.viewers.all():
        if user == post.author:
            return # We don't need to tell someone they made a post
        notify.send(post.author, recipient=post.author, verb="comment on post", target=post.workgroup,
                    comment=_('%(op)s made a new post "%(post)s" in the workgroup "%(workgroup)s" ')
                    % {'op':post.author, 'post':post.title, 'workgroup':post.workgroup})

# Loads example data, this is never used in formal testing.
def exampleData(): # pragma: no cover

    sys_wg,c = Workgroup.objects.get_or_create(name="System Workgroup")
    unitsOfMeasure = [
        ("Length", [
         ("Millimetre", "mm"),
        ]),
        ("Time", [
         ("Hour and minute", ""),
         ("Week", ""),
        ]),
    ]
    for measure,units in unitsOfMeasure:
        m,created = Measure.objects.get_or_create(name=measure,description="")
        print("making measure: {name}".format(name=measure),end="")
        print("  : units of measure:  ",end="")
        for name,symbol in units:
            u,created = UnitOfMeasure.objects.get_or_create(name=name,symbol=symbol,measure=m,workgroup=sys_wg)
            print("{name}".format(name=name),end="")
        print("")
    #defaultData()
    print("configuring users")

    if not User.objects.filter(username__iexact='possum').first():
        user = User.objects.create_superuser('possum','','pilches')
        print("making superuser")

    #Set up based workgroup and workers
    pw,c = Workgroup.objects.get_or_create(name="Possum Workgroup")
    users = [('vicky','Viewer'),
             ('stewie','Steward'),
             ('mandy','Manager'),
             ('suzie','Submitter'),
            ]
    for name,role in users:
        user = User.objects.filter(username__iexact=name).first()
        if not user:
            user = User.objects.create_user(name,'',role)
            print("making user: {name}".format(name=name))
        user.first_name=name.title()
        user.last_name=role
        print("updated user's name to {fn} {ln}".format(fn=user.first_name,ln=user.last_name))
        pw.giveRoleToUser(role.lower(),user)
        user.save()

    oldoc,c  = ObjectClass.objects.get_or_create(name="Person",
            workgroup=pw,description="A human being, whether man or woman.")
    oc,c  = ObjectClass.objects.get_or_create(name="Person",
            workgroup=pw,description="A human being, whether man, woman or child.")
    oc.synonyms = "People"
    oc.readyToReview = True
    oc.save()
    oldoc.superseded_by = oc
    oldoc.save()
    p,c   = Property.objects.get_or_create(name="Age",
            workgroup=pw,description="The length of life or existence.")
    dec,c = DataElementConcept.objects.get_or_create(name="Person-Age",
            workgroup=pw,description="The age of the person.",
            objectClass=oc,property=p
            )
    dec,c = DataElementConcept.objects.get_or_create(name="Person-Age",
            workgroup=pw,description="The age of the person.",
            objectClass=oc,property=p
            )
    W,c   = Property.objects.get_or_create(name="Weight",
            workgroup=pw,description="The weight of an object.")
    H,c   = Property.objects.get_or_create(name="Height",
            workgroup=pw,description="The height of an object, usually measured from the ground to its highest point.")
    WW,c = DataElementConcept.objects.get_or_create(name="Person-Weight",
            workgroup=pw,description="The weight of the person.",
            objectClass=oc,property=W
            )
    HH,c = DataElementConcept.objects.get_or_create(name="Person-Height",
            workgroup=pw,description="The height of the person.",
            objectClass=oc,property=H
            )

    vd,c   = ValueDomain.objects.get_or_create(name="Total years N[NN]",
            workgroup=pw,description="Total number of completed years.",
            format = "X[XX]" ,
            maximum_length = 3,
            unit_of_measure = UnitOfMeasure.objects.filter(name__iexact='Week').first(),
            data_type = DataType.objects.filter(name__iexact='Number').first(),
            )
    de,c = DataElement.objects.get_or_create(name="Person-age, total years N[NN]",
            workgroup=pw,description="The age of the person in (completed) years at a specific point in time.",
            dataElementConcept=dec,valueDomain=vd
            )
    p,c   = Property.objects.get_or_create(name="Sex",
            workgroup=pw,description="A gender.")
    dec,c = DataElementConcept.objects.get_or_create(name="Person-Sex",
            workgroup=pw,description="The sex of the person.",
            objectClass=oc,property=p
            )
    vd,c   = ValueDomain.objects.get_or_create(name="Sex Code",
            workgroup=pw,description="A code for sex.",
            format = "X" ,
            maximum_length = 3,
            unit_of_measure = UnitOfMeasure.objects.filter(name__iexact='Week').first(),
            data_type = DataType.objects.filter(name__iexact='Number').first(),
            )
    for val,mean in [(1,'Male'),(2,'Female')]:
        codeVal = PermissibleValue(value=val,meaning=mean,valueDomain=vd,order=1)
        codeVal.save()
    de,c = DataElement.objects.get_or_create(name="Person-sex, Code N",
            workgroup=pw,description="The sex of the person with a code.",
            )
    de.dataElementConcept=dec
    de.valueDomain=vd
    de.save()

    print("Configuring registration authority")
    ra,c = RegistrationAuthority.objects.get_or_create(
                name="Welfare",description="Welfare Authority")
    ra,c = RegistrationAuthority.objects.get_or_create(
                name="Health",description="Health Authority")
    users = [('reggie','Registrar'),
            ]
    pw.registrationAuthorities.add(ra)
    pw.save()
    for name,role in users:
        user = User.objects.filter(username__iexact=name).first()
        if not user:
            user = User.objects.create_user(name,'',role)
            print("making user: {name}".format(name=name))
        user.first_name=name.title()
        user.last_name=role
        ra.giveRoleToUser(role,user)
        user.save()

    #Lets register a thing :/
    reg,c = Status.objects.get_or_create(
            concept=oc,
            registrationAuthority=ra,
            registrationDate = datetime.date(2009,4,28),
            state =  STATES.standard
            )
