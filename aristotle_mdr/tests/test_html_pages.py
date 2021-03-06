from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
import aristotle_mdr.models as models
import aristotle_mdr.perms as perms
from aristotle_mdr.utils import url_slugify_concept

from django.test.utils import setup_test_environment
setup_test_environment()
from aristotle_mdr.tests import utils
import datetime

class AnonymousUserViewingThePages(TestCase):
    def setUp(self):
        from django.test import Client
        self.client = Client()
    def test_homepage(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code,200)
    def test_help_all_items(self):
        response = self.client.get(reverse('aristotle:about_all_items'))
        self.assertEqual(response.status_code,200)
    def test_visible_item(self):
        wg = models.Workgroup.objects.create(name="Setup WG")
        ra = models.RegistrationAuthority.objects.create(name="Test RA")
        wg.registrationAuthorities.add(ra)
        item = models.ObjectClass.objects.create(name="Test OC",workgroup=wg)
        s = models.Status.objects.create(
                concept=item,
                registrationAuthority=ra,
                registrationDate=timezone.now(),
                state=ra.locked_state
                )
        home = self.client.get(url_slugify_concept(item))
        #Anonymous users requesting a hidden page will be redirected to login
        self.assertEqual(home.status_code,302)
        s.state = ra.public_state
        s.save()
        home = self.client.get(url_slugify_concept(item))
        self.assertEqual(home.status_code,200)

class LoggedInViewConceptPages(utils.LoggedInViewPages):
    defaults = {}
    def setUp(self):
        super(LoggedInViewConceptPages, self).setUp()

        self.item1 = self.itemType.objects.create(name="Test Item 1 (visible to tested viewers)",description=" ",workgroup=self.wg1,**self.defaults)
        self.item2 = self.itemType.objects.create(name="Test Item 2 (NOT visible to tested viewers)",description=" ",workgroup=self.wg2,**self.defaults)
        self.item3 = self.itemType.objects.create(name="Test Item 3 (visible to tested viewers)",description=" ",workgroup=self.wg1,**self.defaults)

    def test_su_can_view(self):
        self.login_superuser()
        response = self.client.get(self.get_page(self.item1))
        self.assertEqual(response.status_code,200)
        response = self.client.get(self.get_page(self.item2))
        self.assertEqual(response.status_code,200)

    def test_editor_can_view(self):
        self.login_editor()
        response = self.client.get(self.get_page(self.item1))
        self.assertEqual(response.status_code,200)
        response = self.client.get(self.get_page(self.item2))
        self.assertEqual(response.status_code,403)

    def test_viewer_can_view(self):
        self.login_viewer()
        response = self.client.get(self.get_page(self.item1))
        self.assertEqual(response.status_code,200)
        response = self.client.get(self.get_page(self.item2))
        self.assertEqual(response.status_code,403)

    def test_stubs_redirect_correctly(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:item',args=[self.item1.id]))
        self.assertRedirects(response,url_slugify_concept(self.item1))
        response = self.client.get(reverse('aristotle:item',args=[self.item1.id])+"/not-a-model/fake-name")
        self.assertRedirects(response,url_slugify_concept(self.item1))
        response = self.client.get(reverse('aristotle:item',args=[self.item1.id])+"/this-isnt-even-a-proper-stub")
        self.assertRedirects(response,url_slugify_concept(self.item1))

    def test_viewer_can_view_related_packages(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:itemPackages',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:itemPackages',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_anon_cannot_view_related_packages(self):
        self.logout()
        response = self.client.get(reverse('aristotle:itemPackages',args=[self.item1.id]))
        self.assertEqual(response.status_code,302)
        response = self.client.get(reverse('aristotle:itemPackages',args=[self.item2.id]))
        self.assertEqual(response.status_code,302)

    def test_anon_cannot_view_edit_page(self):
        self.logout()
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item1.id]))
        self.assertEqual(response.status_code,302)
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item2.id]))
        self.assertEqual(response.status_code,302)
    def test_viewer_cannot_view_edit_page(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item1.id]))
        self.assertEqual(response.status_code,403)
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)
    def test_submitter_can_view_edit_page(self):
        self.login_editor()
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_submitter_can_save_via_edit_page(self):
        from django.forms import model_to_dict
        self.login_editor()
        response = self.client.get(reverse('aristotle:edit_item',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        updated_item = dict((k,v) for (k,v) in model_to_dict(response.context['item']).items() if v is not None)
        updated_name = updated_item['name'] + " updated!"
        updated_item['name'] = updated_name
        response = self.client.post(reverse('aristotle:edit_item',args=[self.item1.id]), updated_item)
        self.item1 = self.itemType.objects.get(pk=self.item1.pk)
        self.assertRedirects(response,url_slugify_concept(self.item1))
        self.assertEqual(self.item1.name,updated_name)

    def test_su_can_download_pdf(self):
        self.login_superuser()
        response = self.client.get(reverse('aristotle:download',args=['pdf',self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:download',args=['pdf',self.item2.id]))
        self.assertEqual(response.status_code,200)

    def test_editor_can_download_pdf(self):
        self.login_editor()
        response = self.client.get(reverse('aristotle:download',args=['pdf',self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:download',args=['pdf',self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_viewer_can_download_pdf(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:download',args=['pdf',self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:download',args=['pdf',self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_viewer_cannot_view_supersede_page(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:supersede',args=[self.item1.id]))
        self.assertEqual(response.status_code,403)
        response = self.client.get(reverse('aristotle:supersede',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_editor_can_view_supersede_page(self):
        self.login_editor()
        response = self.client.get(reverse('aristotle:supersede',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:supersede',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)
        response = self.client.get(reverse('aristotle:supersede',args=[self.item3.id]))
        self.assertEqual(response.status_code,200)

    def test_editor_can_use_ready_to_review(self):
        self.login_editor()
        response = self.client.get(reverse('aristotle:mark_ready_to_review',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:mark_ready_to_review',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)
        response = self.client.get(reverse('aristotle:mark_ready_to_review',args=[self.item3.id]))
        self.assertEqual(response.status_code,200)

        self.assertFalse(self.item1.readyToReview)
        response = self.client.post(reverse('aristotle:mark_ready_to_review',args=[self.item1.id]))
        self.assertRedirects(response,url_slugify_concept(self.item1))
        self.item1 = self.itemType.objects.get(id=self.item1.id) # Stupid cache
        self.assertTrue(self.item1.readyToReview)

    def test_viewer_cannot_view_deprecate_page(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:deprecate',args=[self.item1.id]))
        self.assertEqual(response.status_code,403)
        response = self.client.get(reverse('aristotle:deprecate',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_editor_can_view_deprecate_page(self):
        self.login_editor()
        response = self.client.get(reverse('aristotle:deprecate',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:deprecate',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)
        response = self.client.get(reverse('aristotle:deprecate',args=[self.item3.id]))
        self.assertEqual(response.status_code,200)

    def test_help_page_exists(self):
        self.logout()
        response = self.client.get(self.get_help_page())
        self.assertEqual(response.status_code,200)

    def test_viewer_can_view_registration_history(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:registrationHistory',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:registrationHistory',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_anon_cannot_view_registration_history(self):
        self.logout()
        response = self.client.get(reverse('aristotle:registrationHistory',args=[self.item1.id]))
        self.assertEqual(response.status_code,302)
        response = self.client.get(reverse('aristotle:registrationHistory',args=[self.item2.id]))
        self.assertEqual(response.status_code,302)

    def test_viewer_can_view_item_history(self):
        # Workgroup members can see the edit history of items
        self.login_viewer()
        response = self.client.get(reverse('aristotle:item_history',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:item_history',args=[self.item2.id]))
        self.assertEqual(response.status_code,403)

        # Viewers shouldn't even have the link to history on items they arent in the workgroup for
        response = self.client.get(self.item2.get_absolute_url())
        self.assertFalse(reverse('aristotle:item_history',args=[self.item2.id]) in response.content)

        # Viewers will even have the link to history on items they are in the workgroup for
        response = self.client.get(self.item1.get_absolute_url())
        self.assertTrue(reverse('aristotle:item_history',args=[self.item1.id]) in response.content)

    def test_anon_cannot_view_item_history(self):
        self.logout()
        response = self.client.get(reverse('aristotle:item_history',args=[self.item1.id]))
        self.assertEqual(response.status_code,302)
        response = self.client.get(reverse('aristotle:item_history',args=[self.item2.id]))
        self.assertEqual(response.status_code,302)


        #Register to check if link is on page... it shouldn't be
        models.Status.objects.create(
            concept=self.item1,
            registrationAuthority=self.ra,
            registrationDate = datetime.date(2009,4,28),
            state =  models.STATES.standard
            )
        # Anon users shouldn't even have the link to history *any* items
        response = self.client.get(self.item1.get_absolute_url())
        self.assertEqual(response.status_code,200)
        self.assertFalse(reverse('aristotle:item_history',args=[self.item1.id]) in response.content)

    def test_viewer_can_favourite(self):
        self.login_viewer()
        self.assertTrue(perms.user_can_view(self.viewer,self.item1))

        response = self.client.post(reverse('django.contrib.auth.views.login'), {'username': 'vicky', 'password': 'viewer'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.viewer.profile.favourites.count(),0)

        response = self.client.get(reverse('aristotle:toggleFavourite', args=[self.item1.id]))
        self.assertRedirects(response,url_slugify_concept(self.item1))
        self.assertEqual(self.viewer.profile.favourites.count(),1)
        self.assertEqual(self.viewer.profile.favourites.first().item,self.item1)

        response = self.client.get(reverse('aristotle:toggleFavourite', args=[self.item1.id]))
        self.assertRedirects(response,url_slugify_concept(self.item1))
        self.assertEqual(self.viewer.profile.favourites.count(),0)

    def test_registrar_can_change_status(self):
        self.logout()
        self.login_registrar()

        self.assertFalse(perms.user_can_view(self.registrar,self.item1))
        self.item1.readyToReview = True
        self.item1.save()
        self.item1 = self.itemType.objects.get(pk=self.item1.pk)

        self.assertTrue(perms.user_can_view(self.registrar,self.item1))
        self.assertTrue(perms.user_can_change_status(self.registrar,self.item1))

        response = self.client.get(reverse('aristotle:changeStatus',args=[self.item1.id]))
        self.assertEqual(response.status_code,200)

        self.assertEqual(self.item1.statuses.count(),0)
        response = self.client.post(reverse('aristotle:changeStatus',args=[self.item1.id]),
                    {   'registrationAuthorities': [str(self.ra.id)],
                        'state': self.ra.public_state,
                        'changeDetails': "testing",
                        'cascadeRegistration': 0, #no
                    }
                )
        self.assertRedirects(response,url_slugify_concept(self.item1))

        self.assertEqual(self.item1.statuses.count(),1)
        self.item1 = self.itemType.objects.get(pk=self.item1.pk)
        self.assertTrue(self.item1.is_public())

class ObjectClassViewPage(LoggedInViewConceptPages,TestCase):
    url_name='objectClass'
    itemType=models.ObjectClass
    def test_browse(self):
        self.logout()
        response = self.client.get(reverse('aristotle:browse'))
        self.assertTrue(response.status_code,200)
    def test_browse_oc(self):
        self.logout()
        response = self.client.get(reverse('aristotle:browse',args=[self.item1.id]))
        self.assertTrue(response.status_code,200)
class PropertyViewPage(LoggedInViewConceptPages,TestCase):
    url_name='property'
    itemType=models.Property
class UnitOfMeasureViewPage(LoggedInViewConceptPages,TestCase):
    url_name='unitOfMeasure'
    itemType=models.UnitOfMeasure
class ValueDomainViewPage(LoggedInViewConceptPages,TestCase):
    url_name='valueDomain'
    itemType=models.ValueDomain
    def setUp(self):
        super(ValueDomainViewPage, self).setUp()

        for i in range(4):
            models.PermissibleValue.objects.create(
                value=i,meaning="test permissible meaning %d"%i,order=i,valueDomain=self.item1
                )
        for i in range(4):
            models.SupplementaryValue.objects.create(
                value=i,meaning="test supplementary meaning %d"%i,order=i,valueDomain=self.item1
                )

    def loggedin_user_can_use_value_page(self,value_type,current_item,http_code):
        response = self.client.get(reverse('aristotle:valueDomain_edit_values',args=[current_item.id,value_type]))
        self.assertEqual(response.status_code,http_code)

    def submitter_user_can_use_value_edit_page(self,value_type):
        self.login_editor()
        self.loggedin_user_can_use_value_page(value_type,self.item1,200)
        self.loggedin_user_can_use_value_page(value_type,self.item2,403)
        self.loggedin_user_can_use_value_page(value_type,self.item3,200)

        data = {}
        num_vals = getattr(self.item1,value_type+"Values").count()
        i=0
        for i,v in enumerate(getattr(self.item1,value_type+"Values").all()):
            data.update({"form-%d-id"%i: v.pk, "form-%d-order"%i : v.order, "form-%d-value"%i : v.value, "form-%d-meaning"%i : v.meaning+" -updated"})
        data.update({"form-%d-DELETE"%i: 'checked', "form-%d-meaning"%i : v.meaning+" - deleted"}) # delete the last one.
        # now add a new one
        i=i+1
        data.update({"form-%d-order"%i : i, "form-%d-value"%i : 100, "form-%d-meaning"%i : "new value -updated"})

        data.update({
            "form-TOTAL_FORMS":num_vals+1, "form-INITIAL_FORMS": num_vals, "form-MAX_NUM_FORMS":1000,

            })
        response = self.client.post(reverse('aristotle:valueDomain_edit_values',args=[self.item1.id,value_type]),data)
        self.item1 = models.ValueDomain.objects.get(pk=self.item1.pk)

        self.assertTrue(num_vals == getattr(self.item1,value_type+"Values").count())
        new_value_seen = False
        for v in getattr(self.item1,value_type+"Values").all():
            self.assertTrue('updated' in v.meaning) # This will fail if the deleted item isn't deleted
            if v.value == '100':
                new_value_seen = True
        self.assertTrue(new_value_seen)


        # Item is now locked, submitter is no longer able to edit
        models.Status.objects.create(
                concept=self.item1,
                registrationAuthority=self.ra,
                registrationDate=timezone.now(),
                state=self.ra.locked_state
                )

        self.item1 = models.ValueDomain.objects.get(pk=self.item1.pk)
        self.assertTrue(self.item1.is_locked())
        self.assertFalse(perms.user_can_edit(self.editor,self.item1))
        self.loggedin_user_can_use_value_page(value_type,self.item1,403)


    def test_submitter_can_use_permissible_value_edit_page(self):
        self.submitter_user_can_use_value_edit_page('permissible')

    def test_submitter_can_use_supplementary_value_edit_page(self):
        self.submitter_user_can_use_value_edit_page('supplementary')

    def test_su_can_download_pdf(self):
        self.login_superuser()
        response = self.client.get(reverse('aristotle:download',args=['csv-vd',self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:download',args=['csv-vd',self.item2.id]))
        self.assertEqual(response.status_code,200)

    def test_editor_can_download_csv(self):
        self.login_editor()
        response = self.client.get(reverse('aristotle:download',args=['csv-vd',self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:download',args=['csv-vd',self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_viewer_can_download_csv(self):
        self.login_viewer()
        response = self.client.get(reverse('aristotle:download',args=['csv-vd',self.item1.id]))
        self.assertEqual(response.status_code,200)
        response = self.client.get(reverse('aristotle:download',args=['csv-vd',self.item2.id]))
        self.assertEqual(response.status_code,403)

    def test_values_shown_on_page(self):
        self.login_viewer()

        response = self.client.get(self.get_page(self.item1))
        self.assertEqual(response.status_code,200)
        for pv in self.item1.permissiblevalue_set.all():
            self.assertContains(response,pv.meaning,1)
        for sv in self.item1.supplementaryvalue_set.all():
            self.assertContains(response,sv.meaning,1)

class ConceptualDomainViewPage(LoggedInViewConceptPages,TestCase):
    url_name='conceptualDomain'
    itemType=models.ConceptualDomain
class DataElementConceptViewPage(LoggedInViewConceptPages,TestCase):
    url_name='dataElementConcept'
    itemType=models.DataElementConcept
class DataElementViewPage(LoggedInViewConceptPages,TestCase):
    url_name='dataElement'
    itemType=models.DataElement

class DataElementDerivationViewPage(LoggedInViewConceptPages,TestCase):
    url_name='dataelementderivation'
    @property
    def defaults(self):
        return {'derives':models.DataElement.objects.create(name='derivedDE',description="",workgroup=self.wg1)}
    itemType=models.DataElementDerivation

class LoggedInViewUnmanagedPages(utils.LoggedInViewPages):
    defaults = {}
    def setUp(self):
        super(LoggedInViewUnmanagedPages, self).setUp()
        self.item1 = self.itemType.objects.create(name="OC1",**self.defaults)

    def get_page(self,item):
        url_name = "".join(item._meta.verbose_name.title().split())
        url_name = url_name[0].lower() + url_name[1:]
        return reverse('aristotle:%s'%url_name,args=[item.id])

    def test_help_page_exists(self):
        self.logout()
        response = self.client.get(self.get_help_page())
        self.assertEqual(response.status_code,200)

    def test_item_page_exists(self):
        self.logout()
        response = self.client.get(self.get_page(self.item1))
        self.assertEqual(response.status_code,200)

class RegistrationAuthorityViewPage(LoggedInViewUnmanagedPages,TestCase):
    url_name='registrationAuthority'
    itemType=models.RegistrationAuthority

    def setUp(self):
        super(RegistrationAuthorityViewPage, self).setUp()

        self.item2 = models.Package.objects.create(name="OC1",workgroup=self.wg1,**self.defaults)

        s = models.Status.objects.create(
                concept=self.item2,
                registrationAuthority=self.item1,
                registrationDate=timezone.now(),
                state=models.STATES.standard
                )

    def test_view_all_ras(self):
        self.logout()
        response = self.client.get(reverse('aristotle:allRegistrationAuthorities'))
        self.assertTrue(response.status_code,200)

