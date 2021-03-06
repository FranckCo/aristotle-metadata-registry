from __future__ import print_function

from django.contrib.auth.models import User
from django.test import TestCase
from django.test.utils import setup_test_environment
from django.utils.translation import ugettext_lazy as _

from model_utils import Choices

import aristotle_mdr.models as models
import aristotle_mdr.perms as perms
from aristotle_mdr.tests import utils

setup_test_environment()

class SuperuserPermissions(TestCase):
    # All of the below are called with None as a Superuser, by definition *must* be able to edit, view and managed everything. Since a is_superuser chcek is cheap is should be called first, so calling with None checks that there is no other database calls going on.
    def setUp(self):
        self.su=User.objects.create_superuser('super','','user')

    def test_user_can_alter_comment(self):
        self.assertTrue(perms.user_can_alter_comment(self.su,None))
    def test_user_can_alter_post(self):
        self.assertTrue(perms.user_can_alter_post(self.su,None))
    def test_can_view(self):
        self.assertTrue(perms.user_can_view(self.su,None))
    def test_is_editor(self):
        self.assertTrue(perms.user_is_editor(self.su))
    def test_is_registrar(self):
        self.assertTrue(perms.user_is_registrar(self.su))
        ra = models.RegistrationAuthority.objects.create(name="Test RA")
        self.assertTrue(perms.user_is_registrar(self.su,ra))
    def test_is_workgroup_manager(self):
        self.assertTrue(perms.user_is_workgroup_manager(self.su,None))
        wg = models.Workgroup.objects.create(name="Test WG")
        self.assertTrue(perms.user_is_workgroup_manager(self.su,wg))
    def test_can_change_status(self):
        self.assertTrue(perms.user_can_change_status(self.su,None))
    def test_can_edit(self):
        self.assertTrue(perms.user_can_edit(self.su,None))
    def test_in_workgroup(self):
        self.assertTrue(perms.user_in_workgroup(self.su,None))
    def test_can_edit_registration_authority(self):
        ra = models.RegistrationAuthority.objects.create(name="Test RA")
        self.assertTrue(ra.can_edit(self.su))

class UnitOfMeasureVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(UnitOfMeasureVisibility, self).setUp()
        self.item = models.UnitOfMeasure.objects.create(name="Test UOM",workgroup=self.wg)

class ObjectClassVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(ObjectClassVisibility, self).setUp()
        self.item = models.ObjectClass.objects.create(name="Test OC",workgroup=self.wg)
class PropertyVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(PropertyVisibility, self).setUp()
        self.item = models.Property.objects.create(name="Test P",workgroup=self.wg)
class ValueDomainVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(ValueDomainVisibility, self).setUp()
        self.item = models.ValueDomain.objects.create(name="Test VD",
                workgroup=self.wg,
                format = "X" ,
                maximum_length = 3,
                data_type = models.DataType.objects.create(name="Test DT",workgroup=self.wg)
                )
class DataElementConceptVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(DataElementConceptVisibility, self).setUp()
        self.item = models.DataElementConcept.objects.create(name="Test DEC",
            workgroup=self.wg,
            )
class DataElementVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(DataElementVisibility, self).setUp()
        self.item = models.DataElement.objects.create(name="Test DE",
            workgroup=self.wg,
            )
class DataTypeVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(DataTypeVisibility, self).setUp()
        self.item = models.DataType.objects.create(name="Test DT",
            workgroup=self.wg,
            )
class PackageVisibility(utils.ManagedObjectVisibility,TestCase):
    def setUp(self):
        super(PackageVisibility, self).setUp()
        self.item = models.Package.objects.create(name="Test Package",
            workgroup=self.wg,
            )

class WorkgroupPermissions(TestCase):
    def test_workgroup_add_members(self):
        wg = models.Workgroup.objects.create(name="Test WG")
        user = User.objects.create_user('user','','user')

        wg.giveRoleToUser('manager',user)
        self.assertTrue(user in wg.managers.all())
        wg.removeRoleFromUser('manager',user)
        self.assertFalse(user in wg.managers.all())

        wg.giveRoleToUser('viewer',user)
        self.assertTrue(user in wg.viewers.all())
        wg.removeRoleFromUser('viewer',user)
        self.assertFalse(user in wg.viewers.all())

        wg.giveRoleToUser('submitter',user)
        self.assertTrue(user in wg.submitters.all())
        wg.removeRoleFromUser('submitter',user)
        self.assertFalse(user in wg.submitters.all())

        wg.giveRoleToUser('steward',user)
        self.assertTrue(user in wg.stewards.all())
        wg.removeRoleFromUser('steward',user)
        self.assertFalse(user in wg.stewards.all())

class RegistryGroupPermissions(TestCase):
    def test_registration_add_members(self):
        ra = models.RegistrationAuthority.objects.create(name="Test RA")
        user = User.objects.create_user('user','','user')

        ra.giveRoleToUser('registrar',user)
        self.assertTrue(user in ra.registrars.all())
        ra.removeRoleFromUser('registrar',user)
        self.assertFalse(user in ra.registrars.all())

        ra.giveRoleToUser('manager',user)
        self.assertTrue(user in ra.managers.all())
        ra.removeRoleFromUser('manager',user)
        self.assertFalse(user in ra.managers.all())

    def test_RegistrationAuthority_name_change(self):
        ra = models.RegistrationAuthority.objects.create(name="Test RA")
        user = User.objects.create_user('registrar','','registrar')

        # User isn't in RA... yet
        self.assertFalse(perms.user_is_registrar(user,ra))

        # Add user to RA, assert user is in RA
        ra.giveRoleToUser('registrar',user)
        # Caching issue, refresh from DB with correct permissions
        user = User.objects.get(pk=user.pk)
        self.assertTrue(perms.user_is_registrar(user,ra))

        # Change name of RA, assert user is still in RA
        ra.name = "Test RA2"
        ra.save()
        user = User.objects.get(pk=user.pk)
        self.assertTrue(perms.user_is_registrar(user,ra))

        # Add new RA with old RA's name, assert user is not in the new RA
        newRA = models.RegistrationAuthority.objects.create(name="Test RA")
        user = User.objects.get(pk=user.pk)
        self.assertFalse(perms.user_is_registrar(user,newRA))

        # Remove user to RA, assert user is no longer in RA
        ra.removeRoleFromUser('registrar',user)
        # Caching issue, refresh from DB with correct permissions
        user = User.objects.get(pk=user.pk)
        self.assertFalse(perms.user_is_registrar(user,ra))

class UserEditTesting(TestCase):
    def test_canViewProfile(self):
        u1 = User.objects.create_user('user1','','user1')
        u2 = User.objects.create_user('user2','','user2')
        self.assertFalse(perms.user_can_view(u1,u2))
        self.assertFalse(perms.user_can_view(u2,u1))
        self.assertTrue(perms.user_can_view(u1,u1))
        self.assertTrue(perms.user_can_view(u2,u2))
    def test_canEditProfile(self):
        u1 = User.objects.create_user('user1','','user1')
        u2 = User.objects.create_user('user2','','user2')
        self.assertFalse(perms.user_can_edit(u1,u2))
        self.assertFalse(perms.user_can_edit(u2,u1))
        self.assertTrue(perms.user_can_edit(u1,u1))
        self.assertTrue(perms.user_can_edit(u2,u2))


class CustomConceptQuerySetTest(TestCase):
    def test_is_public_as_changes_happen(self):
        # Uses ValueDomain so the querysets don't return things created in `setUpClass`.
        ra = models.RegistrationAuthority.objects.create(name="Test RA",public_state=models.STATES.standard)
        wg = models.Workgroup.objects.create(name="Setup WG")
        wg.registrationAuthorities.add(ra)
        wg.save()
        oc1 = models.ValueDomain.objects.create(name="Test OC1",workgroup=wg,readyToReview=True)
        oc2 = models.ValueDomain.objects.create(name="Test OC2",workgroup=wg)
        user = User.objects.create_superuser('super','','user')

        # Assert no public items
        self.assertEqual(len(models.ValueDomain.objects.all().public()),0)

        # Register OC1 only
        ra.register(oc1,models.STATES.standard,user)

        # Assert only OC1 is public
        self.assertEqual(len(models.ValueDomain.objects.all().public()),1)
        self.assertTrue(oc1 in models.ValueDomain.objects.all().public())
        self.assertTrue(oc2 not in models.ValueDomain.objects.all().public())

        # Deregister OC1
        state=models.STATES.incomplete
        ra.register(oc1,state,user)

        # Assert no public items
        self.assertEqual(len(models.ValueDomain.objects.all().public()),0)


class CustomConceptQuerySetTest_Slow(object):
    @classmethod
    def setUpClass(cls):
        super(CustomConceptQuerySetTest_Slow, cls).setUpClass()
        cls.super_user = User.objects.create_superuser('permission_check_super '+str(cls.workgroup_owner_type),'','user')
        cls.wg_users = []
        cls.ra_users = []
        cls.ras = {}
        p = "permission_check %s "%str(cls.workgroup_owner_type)
        # Default settings for locked/public
        cls.ras['default'] = models.RegistrationAuthority.objects.create(name=p+"Default RA")

        # Locked standards are visible standards
#        cls.ras['standard'] = models.RegistrationAuthority.objects.create(name=p+"Standard RA",public_state=models.STATES.standard,locked_state=models.STATES.standard)

        # Always public, hard to lock
        cls.ras['wiki_like'] = models.RegistrationAuthority.objects.create(name=p+"Wiki RA",public_state=models.STATES.candidate,locked_state=models.STATES.standard)

        # Only public on retirement
        cls.ras['top_secret'] = models.RegistrationAuthority.objects.create(name=p+"CIA RA",public_state=models.STATES.retired)

        for key,ra in cls.ras.items():
            role = 'registrar'
            u = User.objects.create_user(p+role+key,'','user')
            ra.giveRoleToUser(role,u)
            cls.ra_users.append(u)

        cls.wgs = []

        # We use a cut back version of only states needed for the above items, just to reduce the number of items needed to be made.
        used_choices = Choices (
# -exclude (0,'notprogressed',_('Not Progressed')),
# -exclude (1,'incomplete',_('Incomplete')),
           (2,'candidate',_('Candidate')),
           (3,'recorded',_('Recorded')),
# -exclude (4,'qualified',_('Qualified')),
           (5,'standard',_('Standard')),
# -exclude (6,'preferred',_('Preferred Standard')),
# -exclude (7,'superseded',_('Superseded')),
           (8,'retired',_('Retired')),
         )

        print("About to make a *LOT* of items. This may appear to lock up, but it still working.")
        import itertools
        # http://en.wikipedia.org/wiki/Combinatorial_explosion
        for i in range(1,4):
            # Generate a number of different workgroups with different numbers of RAs
            # Each workgroup can have at most 2 RAs in this test, and the third will be
            #  a "non-member" workgroup that we also register the item in to confirm
            #  that "non-members" don't alter the visibility.
            for keys in itertools.combinations(cls.ras.keys(), i):
                prefix = "%d %s %s"%(len(keys),"-".join(keys),str(cls.workgroup_owner_type))
                wg = models.Workgroup.objects.create(name="WG "+prefix,ownership=cls.workgroup_owner_type)

                for role in ['viewer','submitter','steward']:
                    u = User.objects.create_user(role+prefix,'','user')
                    wg.giveRoleToUser(role,u)
                    cls.wg_users.append(u)

                max_ra_index = min(2,len(keys))
                for ra_key in keys[:max_ra_index]:
                    wg.registrationAuthorities.add(cls.ras[ra_key])
                cls.wgs.append(wg)

                # now we create every possible combination of states for the keys
                # eg. the cartesian product of the States
                for states in [s for s in itertools.product(used_choices,repeat=len(keys))]:
                    # we create an item registered with that set of states in a bunch of RAs
                    item = models.ObjectClass.objects.create(name="Concept %s"%(prefix),description="",workgroup=wg)
                    print('+', end="")
                    # Then register it
                    for ra,state in zip(keys,states):
                        ra = cls.ras[ra_key]
                        state = state[0]
                        ra.register(item,models.STATES.standard,cls.super_user)
        print("Created this many things to test against:", models.ObjectClass.objects.count())

    def test_is_public(self):
        invalid_items = []
        for user in self.wg_users + self.ra_users:
            for item in models.ObjectClass.objects.all().public():
                if not item.is_public(): #pragma: no cover
                    # This branch needs no coverage as it shouldn't be hit
                    invalid_items.append((user,item))
        if len(invalid_items) > 0: #pragma: no cover
            # This branch needs no coverage as it shouldn't be hit
            print("These items failed the check for ConceptQuerySet.public")
            for user,item in invalid_items:
                print("user=",user)
                print("item=",item)
                print("     ",item.statuses.all())

    def abstract_queryset_check(self,queryset,permission,name):
        invalid_items = []
        # This verifies that everything that is returned in the given QuerySet has the right permission
        # However, it doesn't verify that every item has that permisison for a the user will be returned.
        # i.e. We assure that nothing "uneditable" is returned, not that everything "editable" is.
        # i.e. We assure that nothing "invisible" is returned, not that everything "visible" is.
        # TODO: Expand the below.
        for user in self.wg_users + self.ra_users:
            for item in queryset(user):
                if not permission(user,item): #pragma: no cover
                    # This branch needs no coverage as it shouldn't be hit
                    invalid_items.append((user,item))
        if len(invalid_items) > 0: #pragma: no cover
            # This branch needs no coverage as it shouldn't be hit
            print("These items failed the check for %s:"%name)
            for user,item in invalid_items:
                print("user=",user)
                print("item=",item)
                print("     ",item.statuses.all())
        self.assertEqual(len(invalid_items),0)

    def test_is_editable(self):
        self.abstract_queryset_check(
                queryset=models.ObjectClass.objects.editable,
                permission=perms.user_can_edit,
                name="ConceptQuerySet.editable()"
            )

    def test_is_visible(self):
        self.abstract_queryset_check(
                queryset=models.ObjectClass.objects.visible,
                permission=perms.user_can_view,
                name="ConceptQuerySet.visible()"
            )

    def test_querysets_for_superuser(self):
        user = User.objects.create_superuser('super','','user')
        self.assertTrue(models.ObjectClass.objects.visible(user).count() == models.ObjectClass.objects.all().count())
        self.assertTrue(models.ObjectClass.objects.editable(user).count() == models.ObjectClass.objects.all().count())

class CustomConceptQuerySetTest_RegistrationOwned_Slow(CustomConceptQuerySetTest_Slow,TestCase):
    workgroup_owner_type = models.WORKGROUP_OWNERSHIP.registry
class CustomConceptQuerySetTest_RegistryOwned_Slow(CustomConceptQuerySetTest_Slow,TestCase):
    workgroup_owner_type = models.WORKGROUP_OWNERSHIP.authority

class RegistryCascadeTest(TestCase):
    def test_superuser_DataElementConceptCascade(self):
        user = User.objects.create_superuser('super','','user')
        self.ra = models.RegistrationAuthority.objects.create(name="Test RA")
        self.wg = models.Workgroup.objects.create(name="Setup WG")
        self.wg.registrationAuthorities.add(self.ra)
        self.wg.save()
        self.oc = models.ObjectClass.objects.create(name="Test OC",workgroup=self.wg,readyToReview=True)
        self.pr = models.Property.objects.create(name="Test P",workgroup=self.wg,readyToReview=True)
        self.dec = models.DataElementConcept.objects.create(name="Test DEC",readyToReview=True,
            objectClass=self.oc,
            property=self.pr,
            workgroup=self.wg,
            )

        self.assertEqual(self.oc.statuses.count(),0)
        self.assertEqual(self.pr.statuses.count(),0)
        self.assertEqual(self.dec.statuses.count(),0)

        state=models.STATES.candidate
        self.ra.register(self.dec,state,user)
        self.assertEqual(self.oc.statuses.count(),0)
        self.assertEqual(self.pr.statuses.count(),0)
        self.assertEqual(self.dec.statuses.count(),1)

        state=models.STATES.standard
        self.ra.register(self.dec,state,user,cascade=True)
        self.assertEqual(self.dec.statuses.count(),1)
        self.assertEqual(self.oc.statuses.count(),1)
        self.assertEqual(self.pr.statuses.count(),1)

        self.assertEqual(self.oc.statuses.all()[0].state,state)
        self.assertEqual(self.pr.statuses.all()[0].state,state)
        self.assertEqual(self.dec.statuses.all()[0].state,state)

    def test_superuser_DataElementCascade(self):
        user = User.objects.create_superuser('super','','user')
        self.ra = models.RegistrationAuthority.objects.create(name="Test RA")
        self.wg = models.Workgroup.objects.create(name="Setup WG")
        self.wg.registrationAuthorities.add(self.ra)
        self.wg.save()
        self.oc = models.ObjectClass.objects.create(name="Test OC",workgroup=self.wg,readyToReview=True)
        self.pr = models.Property.objects.create(name="Test P",workgroup=self.wg,readyToReview=True)
        self.vd = models.ValueDomain.objects.create(name="Test VD",readyToReview=True,
                workgroup=self.wg,
                format = "X" ,
                maximum_length = 3,
                data_type = models.DataType.objects.create(name="Test DT",workgroup=self.wg)
                )
        self.dec = models.DataElementConcept.objects.create(name="Test DEC",readyToReview=True,
            objectClass=self.oc,
            property=self.pr,
            workgroup=self.wg,
            )
        self.de = models.DataElement.objects.create(name="Test DE",readyToReview=True,
            dataElementConcept=self.dec,
            valueDomain=self.vd,
            workgroup=self.wg,
            )

        self.assertEqual(self.oc.statuses.count(),0)
        self.assertEqual(self.pr.statuses.count(),0)
        self.assertEqual(self.vd.statuses.count(),0)
        self.assertEqual(self.dec.statuses.count(),0)
        self.assertEqual(self.de.statuses.count(),0)

        state=models.STATES.candidate
        self.ra.register(self.de,state,user)
        self.assertEqual(self.oc.statuses.count(),0)
        self.assertEqual(self.pr.statuses.count(),0)
        self.assertEqual(self.vd.statuses.count(),0)
        self.assertEqual(self.dec.statuses.count(),0)
        self.assertEqual(self.de.statuses.count(),1)

        state=models.STATES.standard
        self.ra.register(self.de,state,user,cascade=True)
        self.assertEqual(self.de.statuses.count(),1)
        self.assertEqual(self.dec.statuses.count(),1)
        self.assertEqual(self.vd.statuses.count(),1)
        self.assertEqual(self.oc.statuses.count(),1)
        self.assertEqual(self.pr.statuses.count(),1)

        self.assertEqual(self.oc.statuses.all()[0].state,state)
        self.assertEqual(self.pr.statuses.all()[0].state,state)
        self.assertEqual(self.vd.statuses.all()[0].state,state)
        self.assertEqual(self.dec.statuses.all()[0].state,state)
        self.assertEqual(self.de.statuses.all()[0].state,state)

