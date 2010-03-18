# Copyright 2008-2009 Brian Boyer, Ryan Mark, Angela Nitzke, Joshua Pollock,
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

from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.contrib.auth import authenticate, login, logout, REDIRECT_FIELD_NAME
from django.contrib.auth.models import User
from django.conf import settings

from facebookconnect.models import FacebookProfile


def facebook_login(request, redirect_url=None, template_name='facebook/login.html'):
    """
    Log in a facebook user

    Usually handles the django side of what happens when you click the
    facebook connect button. The user will get redirected to the 'setup' view
    if thier facebook account is not on file. If the user is on file, they
    will get redirected. You can specify the redirect url in the following
    order of precedence:

        1.  whatever url is in the 'next' get parameter passed to the
            facebook_login url 
        2.  whatever url is passed to the facebook_login view when the url 
            is defined 
        3.  whatever url is defined in the LOGIN_REDIRECT_URL setting directive

    Sending a user here without login will display a login template.

    Params: 
    
        *   redirect_url: defines where to send the user after they are
            logged in. This can get overridden by the url in the 'next' get 
            param passed on the url. 
        *   template_name: Template to use if a user arrives at this page 
            without submitting to it. Uses 'facebook/login.html' by default.
            
    """
    # determine redirect url in order of priority
    passed_redirect_url = request.REQUEST.get(REDIRECT_FIELD_NAME, None)
    set_redirect_url = getattr(settings, "LOGIN_REDIRECT_URL", "/")
    redirect_url = redirect_url or passed_redirect_url or set_redirect_url
    
    # User is logging in
    if request.method == 'POST':
        user = authenticate(request=request)
        if user:
            if not user.is_active:
                raise FacebookAuthError('This account is disabled.')            
            login(request, user)
            return HttpResponseRedirect(redirect_url)
        elif request.facebook.uid:
            # created profile object and dummy django user
            profile = FacebookProfile(facebook_id=request.facebook.uid)
            user = User(username=request.facebook.uid, email=profile.email, 
                first_name=profile.first_name, last_name=profile.last_name)
            user.set_unusable_password()
            user.save()
            profile.user = user
            profile.save()
            user = authenticate(request=request)
            login(request, user)
            return HttpResponseRedirect(redirect_url)
            
    # User is already logged in
    elif request.user.is_authenticated():
        return HttpResponseRedirect(redirect_url)

    return render_to_response(template_name, {
        REDIRECT_FIELD_NAME: redirect_url
    }, context_instance=RequestContext(request))

    
def facebook_logout(request, redirect_url=None):
    """
    Logs a user out of facebook and django.
    
    Params:
    
        *   redirect_url: destination after the user is logged out - defaults
            to the 'LOGOUT_REDIRECT_URL' setting.
            
    """
    logout(request)
    try:
        request.facebook.session_key = None
        request.facebook.uid = None
    except AttributeError:
        pass
    url = getattr(settings, 'LOGOUT_REDIRECT_URL', redirect_url) or '/'
    return HttpResponseRedirect(url)
    

class FacebookAuthError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)
    