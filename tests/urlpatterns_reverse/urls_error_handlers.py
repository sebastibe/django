# Used by the ErrorHandlerResolutionTests test case.

from django.conf.urls import patterns

urlpatterns = patterns('')

handler404 = 'urlpatterns_reverse.views.empty_view'
handler500 = 'urlpatterns_reverse.views.empty_view'
