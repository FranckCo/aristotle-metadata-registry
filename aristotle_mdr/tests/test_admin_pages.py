from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.utils import setup_test_environment

import aristotle_mdr.models as models
import aristotle_mdr.tests.utils as utils

setup_test_environment()

class AdminPage(utils.LoggedInViewPages,TestCase):
    def setUp(self):
        super(AdminPage, self).setUp()

    def test_clone(self):
        from aristotle_mdr.utils import concept_to_clone_dict

        # Does cloning an item prepopulate everythin?
        self.login_editor()
        oc = models.ObjectClass.objects.create(name="OC1",workgroup=self.wg1)
        prop = models.Property.objects.create(name="Prop1",workgroup=self.wg1)
        dec = models.DataElementConcept.objects.create(name="DEC1",objectClass=oc,property=prop,workgroup=self.wg1)

        response = self.client.get(reverse("admin:aristotle_mdr_dataelementconcept_add")+"?clone=%s"%dec.id)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['adminform'].form.initial,concept_to_clone_dict(dec))

    def test_name_suggests(self):
        self.login_editor()
        oc = models.ObjectClass.objects.create(name="OC1",workgroup=self.wg1)
        prop = models.Property.objects.create(name="Prop1",workgroup=self.wg1)
        dec = models.DataElementConcept.objects.create(name="DEC1",objectClass=oc,property=prop,workgroup=self.wg1)

        response = self.client.get(reverse("admin:aristotle_mdr_dataelementconcept_change",args=[dec.pk]))
        self.assertEqual(response.status_code,200)

    def test_su_can_add_new_user(self):
        self.login_superuser()
        response = self.client.post(reverse("admin:auth_user_add"),
            {'username':"newuser",'password1':"test",'password2':"test",
                'profile-TOTAL_FORMS': 1, 'profile-INITIAL_FORMS': 0, 'profile-MAX_NUM_FORMS': 1,
                'profile-0-workgroup_manager_in': [self.wg1.id],
                'profile-0-steward_in': [self.wg1.id],
                'profile-0-submitter_in': [self.wg1.id],
                'profile-0-viewer_in': [self.wg1.id],
                'profile-0-registrationauthority_manager_in': [self.ra.id],
                'profile-0-registrar_in': [self.ra.id],

            }
        )
        self.assertEqual(response.status_code,302)
        new_user = User.objects.get(username='newuser')
        self.assertEqual(new_user.profile.workgroups.count(),1)
        self.assertEqual(new_user.profile.workgroups.first(),self.wg1)
        self.assertEqual(new_user.profile.registrarAuthorities.count(),1)
        self.assertEqual(new_user.profile.registrarAuthorities.first(),self.ra)
        for rel in [new_user.workgroup_manager_in,
                    new_user.steward_in,
                    new_user.submitter_in,
                    new_user.viewer_in]:
            self.assertEqual(rel.count(),1)
            self.assertEqual(rel.first(),self.wg1)
        for rel in [new_user.registrationauthority_manager_in,
                    new_user.registrar_in,]:
            self.assertEqual(rel.count(),1)
            self.assertEqual(rel.first(),self.ra)

        response = self.client.post(reverse("admin:auth_user_add"),
            {'username':"newuser_with_none",'password1':"test",'password2':"test",
                'profile-TOTAL_FORMS': 1, 'profile-INITIAL_FORMS': 0, 'profile-MAX_NUM_FORMS': 1,
            }
        )
        self.assertEqual(response.status_code,302)
        new_user = User.objects.get(username='newuser_with_none')
        self.assertEqual(new_user.profile.workgroups.count(),0)
        self.assertEqual(new_user.profile.registrarAuthorities.count(),0)
        for rel in [new_user.workgroup_manager_in,
                    new_user.steward_in,
                    new_user.submitter_in,
                    new_user.viewer_in]:
            self.assertEqual(rel.count(),0)
        for rel in [new_user.registrationauthority_manager_in,
                    new_user.registrar_in,]:
            self.assertEqual(rel.count(),0)


    def test_editor_can_view_admin_page(self):
        self.login_editor()
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code,200)

class AdminPageForConcept(utils.LoggedInViewPages):
    form_defaults = {}
    create_defaults = {}
    def setUp(self,instant_create=True):
        super(AdminPageForConcept, self).setUp()
        if instant_create:
            self.create_items()

    def create_items(self):
        self.item1 = self.itemType.objects.create(name="admin_page_test_oc",description=" ",workgroup=self.wg1,**self.create_defaults)

    def test_editor_make_item(self):
        self.login_editor()

        before_count = self.wg1.items.count()
        response = self.client.get(reverse("admin:%s_%s_changelist"%(self.itemType._meta.app_label,self.itemType._meta.model_name)))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse("admin:%s_%s_add"%(self.itemType._meta.app_label,self.itemType._meta.model_name)))
        self.assertEqual(response.status_code,200)
        # make an item
        response = self.client.get(reverse("admin:%s_%s_add"%(self.itemType._meta.app_label,self.itemType._meta.model_name)))

        data = {'name':"admin_page_test_oc",'description':"test","workgroup":self.wg1.id,
                    'statuses-TOTAL_FORMS': 0, 'statuses-INITIAL_FORMS': 0 #no substatuses
                }
        data.update(self.form_defaults)

        response = self.client.post(reverse("admin:%s_%s_add"%(self.itemType._meta.app_label,self.itemType._meta.model_name)),data)

        self.assertEqual(response.status_code,302)
        self.assertRedirects(response,reverse("admin:%s_%s_changelist"%(self.itemType._meta.app_label,self.itemType._meta.model_name)))
        self.assertEqual(self.wg1.items.first().name,"admin_page_test_oc")
        self.assertEqual(self.wg1.items.count(),before_count+1)

        # Editor can't save in WG2, so this won't redirect.
        data.update({"workgroup":self.wg2.id})
        response = self.client.post(reverse("admin:%s_%s_add"%(self.itemType._meta.app_label,self.itemType._meta.model_name)),data)

        self.assertEqual(self.wg2.items.count(),0)
        self.assertEqual(response.status_code,200)

    def test_editor_deleting_allowed_item(self):
        self.login_editor()
        # make some items

        before_count = self.wg1.items.count()
        self.assertEqual(self.wg1.items.count(),1)
        response = self.client.get(reverse("admin:%s_%s_delete"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]))
        self.assertEqual(response.status_code,200)
        response = self.client.post(
            reverse("admin:%s_%s_delete"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]),
            {'post':'yes'}
            )
        self.assertRedirects(response,reverse("admin:%s_%s_changelist"%(self.itemType._meta.app_label,self.itemType._meta.model_name)))
        self.assertEqual(self.wg1.items.count(),before_count-1)

        self.item1 = self.itemType.objects.create(name="OC1",workgroup=self.wg1,readyToReview=True, **self.create_defaults)
        self.assertEqual(self.wg1.items.count(),1)
        before_count = self.wg1.items.count()
        self.ra.register(self.item1,models.STATES.standard,self.registrar)
        self.assertTrue(self.item1.is_registered)

        before_count = self.wg1.items.count()
        response = self.client.get(reverse("admin:%s_%s_delete"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]))
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.wg1.items.count(),before_count)
        response = self.client.post(
            reverse("admin:%s_%s_delete"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]),
            {'post':'yes'}
            )
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.wg1.items.count(),before_count)

    def test_editor_deleting_forbidden_item(self):
        self.login_editor()
        self.item2 = self.itemType.objects.create(name="OC2",workgroup=self.wg2, **self.create_defaults)

        before_count = self.wg2.items.count()
        response = self.client.get(reverse("admin:%s_%s_delete"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item2.pk]))
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.wg2.items.count(),before_count)

        before_count = self.wg2.items.count()
        response = self.client.post(
            reverse("admin:%s_%s_delete"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item2.pk]),
            {'post':'yes'}
            )
        self.assertEqual(response.status_code,404)
        self.assertEqual(self.wg2.items.count(),before_count)

    def test_editor_change_item(self):
        from django.forms import model_to_dict
        self.login_editor()
        response = self.client.get(reverse("admin:%s_%s_change"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]))
        self.assertEqual(response.status_code,200)

        updated_item = dict((k,v) for (k,v) in model_to_dict(self.item1).items() if v is not None)
        updated_name = updated_item['name'] + " updated!"
        updated_item['name'] = updated_name

        updated_item.update({
            'statuses-TOTAL_FORMS': 0, 'statuses-INITIAL_FORMS': 0 #no statuses
        })
        updated_item.update(self.form_defaults)

        response = self.client.post(
                reverse("admin:%s_%s_change"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]),
                updated_item
                )
        self.item1 = self.itemType.objects.get(pk=self.item1.pk)
        self.assertEqual(self.item1.name,updated_name)

#deprecated
    def test_supersedes_saves(self):
        self.item2 = self.itemType.objects.create(name="admin_page_test_oc_2",description=" ",workgroup=self.wg1,**self.create_defaults)
        self.item3 = self.itemType.objects.create(name="admin_page_test_oc_2",description=" ",workgroup=self.wg1,**self.create_defaults)

        from django.forms import model_to_dict
        self.login_editor()
        response = self.client.get(reverse("admin:%s_%s_change"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]))
        self.assertEqual(response.status_code,200)

        updated_item = dict((k,v) for (k,v) in model_to_dict(self.item1).items() if v is not None)
        updated_name = updated_item['name'] + " updated!"
        updated_item['name'] = updated_name

        updated_item.update({
            'statuses-TOTAL_FORMS': 0, 'statuses-INITIAL_FORMS': 0, #no statuses
            'deprecated':[self.item2.id,self.item3.id]
        })
        updated_item.update(self.form_defaults)

        response = self.client.post(
                reverse("admin:%s_%s_change"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]),
                updated_item
                )
        self.item1 = self.itemType.objects.get(pk=self.item1.pk)
        self.assertTrue(self.item2 in self.item1.supersedes.all())
        self.assertTrue(self.item3 in self.item1.supersedes.all())

    def test_superseded_by_saves(self):
        self.item2 = self.itemType.objects.create(name="admin_page_test_oc_2",description=" ",workgroup=self.wg1,**self.create_defaults)

        from django.forms import model_to_dict
        self.login_editor()
        response = self.client.get(reverse("admin:%s_%s_change"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]))
        self.assertEqual(response.status_code,200)

        updated_item = dict((k,v) for (k,v) in model_to_dict(self.item1).items() if v is not None)
        updated_name = updated_item['name'] + " updated!"
        updated_item['name'] = updated_name

        updated_item.update({
            'statuses-TOTAL_FORMS': 0, 'statuses-INITIAL_FORMS': 0, #no statuses
            'superseded_by':self.item2.id
        })
        updated_item.update(self.form_defaults)

        response = self.client.post(
                reverse("admin:%s_%s_change"%(self.itemType._meta.app_label,self.itemType._meta.model_name),args=[self.item1.pk]),
                updated_item
                )
        self.item1 = self.itemType.objects.get(pk=self.item1.pk)
        self.assertTrue(self.item2 == self.item1.superseded_by)



class ObjectClassAdminPage(AdminPageForConcept,TestCase):
    itemType=models.ObjectClass
class PropertyAdminPage(AdminPageForConcept,TestCase):
    itemType=models.Property
class ValueDomainAdminPage(AdminPageForConcept,TestCase):
    itemType=models.ValueDomain
    form_defaults={
        'permissiblevalue_set-TOTAL_FORMS':0,
        'permissiblevalue_set-INITIAL_FORMS':0,
        'permissiblevalue_set-MAX_NUM_FORMS':1,
        'supplementaryvalue_set-TOTAL_FORMS':0,
        'supplementaryvalue_set-INITIAL_FORMS':0,
        'supplementaryvalue_set-MAX_NUM_FORMS':1,
        }
class ConceptualDomainAdminPage(AdminPageForConcept,TestCase):
    itemType=models.ConceptualDomain
class DataElementConceptAdminPage(AdminPageForConcept,TestCase):
    itemType=models.DataElementConcept
class DataElementAdminPage(AdminPageForConcept,TestCase):
    itemType=models.DataElement
class DataTypeAdminPage(AdminPageForConcept,TestCase):
    itemType=models.DataType
class DataElementDerivationAdminPage(AdminPageForConcept,TestCase):
    itemType=models.DataElementDerivation
    def setUp(self):
        super(DataElementDerivationAdminPage, self).setUp(instant_create=False)
        self.ded_wg = models.Workgroup.objects.create(name="Derived WG")
        self.derived_de = models.DataElement.objects.create(name='derivedDE',description="",workgroup=self.ded_wg)
        self.ra.register(self.derived_de,models.STATES.standard,self.registrar)
        self.create_defaults = {'derives':self.derived_de}
        self.form_defaults = {'derives':self.derived_de.id}
        self.create_items()

