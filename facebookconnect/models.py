# Copyright 2008 Brian Boyer, Ryan Mark, Angela Nitzke, Joshua Pollock,
# Stuart Tiffen, Kayla Webley and the Medill School of Journalism, Northwestern
# University.
#
# This file is part of django-facebookconnect.
#
# django-facebookconnect is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# django-facebookconnect is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
#You should have received a copy of the GNU General Public License
#along with django-facebookconnect.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import logging
import sha, random
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from facebook.djangofb import Facebook,get_facebook_client
from facebook import FacebookError
from urllib2 import URLError

FACEBOOK_FIELDS = ['uid,name,first_name,pic_square_with_logo,affiliations,status,proxied_email']
DEFAULT_DUMMY_FACEBOOK_INFO = {
    'uid':0,
    'name':'(Private)',
    'first_name':'(Private)',
    'pic_square_with_logo':'/public/images/t_silhouette.jpg',
    'affiliations':None,
    'status':None,
    'proxied_email':None,
}

class FacebookBackend:
    def authenticate(self, request=None):
        fb = get_facebook_client()
        fb.check_session(request)
        if fb.uid:
            try:
                logging.debug("Checking for Facebook Profile %s..." % fb.uid)
                fbprofile = FacebookProfile.objects.get(facebook_id=fb.uid)
                return fbprofile.user
            except FacebookProfile.DoesNotExist:
                logging.debug("FB account hasn't been used before...")
                return None
        else:
            logging.debug("Invalid Facebook login for %s" % fb.__dict__)
            return None
        
    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
        
class BigIntegerField(models.IntegerField):
    empty_strings_allowed=False
    def get_internal_type(self):
        return "BigIntegerField"
    
    def db_type(self):
        if settings.DATABASE_ENGINE == 'oracle':
            return "NUMBER(19)"
        else:
            return "bigint"

class FacebookTemplate(models.Model):
    name = models.SlugField(unique=True)
    template_bundle_id = BigIntegerField()
    
    def __unicode__(self):
        return self.name.capitalize()

class FacebookProfile(models.Model):
    user = models.OneToOneField(User,related_name="facebook_profile")
    facebook_id = models.IntegerField(unique=True)
    
    __facebook_info = None
    
    def __get_picture_url(self):
        self.__configure_me()
        if self.__facebook_info['pic_square_with_logo']:
            return self.__facebook_info['pic_square_with_logo']
        else:
            return getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO)['pic_square_with_logo']
    picture_url = property(__get_picture_url)

    def __get_profile_url(self):
        return u"http://www.facebook.com/profile.php?id=%s" % (self.facebook_id)
    profile_url = property(__get_profile_url)
    
    def __get_full_name(self):
        self.__configure_me()
        if self.__facebook_info['name']:
            return u"%s" % self.__facebook_info['name']
        else:
            return getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO)['name']
    full_name = property(__get_full_name)
    
    def __get_first_name(self):
        self.__configure_me()
        if self.__facebook_info['first_name']:
            return u"%s" % self.__facebook_info['first_name']
        else:
            return getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO)['first_name']
    first_name = property(__get_first_name)
    
    def __get_networks(self):
        self.__configure_me()
        return self.__facebook_info['affiliations']
    networks = property(__get_networks)
    
    def __get_status(self):
        self.__configure_me()
        if self.__facebook_info['status']:
            return self.__facebook_info['status']['message']
        else:
            return ""
    status = property(__get_status)

    def __get_email(self):
        self.__configure_me()
        if self.__facebook_info['proxied_email']:
            return self.__facebook_info['proxied_email']
        else:
            return ""
    email = property(__get_email)

    def get_friends_profiles(self,limit=50):
        '''returns primed profile objects for this persons friends'''
        friends = []
        friends_info = []
        friends_ids = []
        try:
            friends_ids = self.__get_facebook_friends()
        except (FacebookError,URLError), ex:
            logging.error("Facebook Fail getting friends: %s" % ex)
        logging.debug("Friends of %s %s" % (self.facebook_id,friends_ids))
        if len(friends_ids) > 0:
            #this will cache all the friends in one api call
            self.__get_facebook_info(friends_ids)
        for id in friends_ids:
            try:
                friends.append(FacebookProfile.objects.get(facebook_id=id))
            except (User.DoesNotExist, FacebookProfile.DoesNotExist):
                logging.error("Can't find friend profile %s" % id)
        return friends
            
    def facebook_only(self):
        """return true if this user uses facebook and only facebook"""
        if self.facebook_id and self.facebook_id == self.user.username:
            return True
        else:
            return False

    def __get_facebook_friends(self):
        _facebook_obj = get_facebook_client()
        friends = []
        cache_key = 'fb_friends_%s' % (self.facebook_id)
    
        fb_info_cache = cache.get(cache_key)
        if fb_info_cache:
            friends = fb_info_cache
        else:
            if getattr(settings,'RANDOM_FACEBOOK_FAIL',False) and random.randint(1,10) is 8:
                raise FacebookError(102,"RANDOM FACEBOOK FAIL!!!",[])
            elif getattr(settings,'RANDOM_FACEBOOK_FAIL',False) and random.randint(1,10) is 3:
                raise URLError(104)
            logging.debug("Calling Facebook for '%s'" % cache_key)
            friends = _facebook_obj.friends.getAppUsers()
            cache.set(cache_key,friends,getattr(settings,'FACEBOOK_CACHE_TIMEOUT',1800))
        
        return friends        

    def __get_facebook_info(self,fbids):
        _facebook_obj = get_facebook_client()
        ret = []
        ids_to_get = []
        for id in fbids:
            if id is 0:
                ret.append(getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO))
            
            if _facebook_obj.uid is None:
                cache_key = 'fb_user_info_%s' % id
            else:
                cache_key = 'fb_user_info_%s_%s' % (_facebook_obj.uid,id)
        
            fb_info_cache = cache.get(cache_key)
            if fb_info_cache:
                ret.append(fb_info_cache)
            else:
                ids_to_get.append(id)
        
        if len(ids_to_get) > 0:
            if getattr(settings,'RANDOM_FACEBOOK_FAIL',False) and random.randint(1,10) is 8:
                raise FacebookError(102,"RANDOM FACEBOOK FAIL!!!",[])
            elif getattr(settings,'RANDOM_FACEBOOK_FAIL',False) and random.randint(1,10) is 3:
                raise URLError(104)
            logging.debug("Calling Facebook for '%s'" % ids_to_get)
            tmp_info = _facebook_obj.users.getInfo(ids_to_get, FACEBOOK_FIELDS)
            
            ret.extend(tmp_info)
            for info in tmp_info:
                if _facebook_obj.uid is None:
                    cache_key = 'fb_user_info_%s' % id
                else:
                    cache_key = 'fb_user_info_%s_%s' % (_facebook_obj.uid,info['uid'])

                cache.set(cache_key,info,getattr(settings,'FACEBOOK_CACHE_TIMEOUT',1800))
                
        return ret

    def __configure_me(self):
        try:
            logging.debug("FBID: '%s' profile: '%s' user: '%s'" % (self.facebook_id,self.id,self.user_id))
            if self.__facebook_info == getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO) or not self.__facebook_info:
                self.__facebook_info = self.__get_facebook_info([self.facebook_id])[0]
        except (ImproperlyConfigured), ex:
            logging.error('Facebook not setup')
        except (FacebookError,URLError), ex:
            logging.error('Facebook Fail loading profile: %s' % ex)
            self.__facebook_info = getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO)
        except (IndexError), ex:
            logging.error("Couldn't retrieve FB info for FBID: '%s' profile: '%s' user: '%s'" % (self.facebook_id,self.id,self.user_id))
            self.__facebook_info = getattr(settings,"DUMMY_FACEBOOK_INFO",DEFAULT_DUMMY_FACEBOOK_INFO)

    def get_absolute_url(self):
        return self.__get_profile_url()

    def __unicode__(self):
        return "FacebookProfile for %s" % self.facebook_id