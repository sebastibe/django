import re
import logging
from StringIO import StringIO
import zlib

from django import http
from django.conf import settings
from django.core.handlers.wsgi import LimitedStream
from django.utils.text import compress_sequence, compress_string
from django.utils.cache import patch_vary_headers

re_accepts_gzip = re.compile(r'\bgzip\b')

logger = logging.getLogger('django.request')


class GZipMiddleware(object):
    """
    This middleware compresses content if the browser allows gzip compression.
    It sets the Vary header accordingly, so that caches will base their storage
    on the Accept-Encoding header.
    """
    def process_response(self, request, response):
        # It's not worth attempting to compress really short responses.
        if not response.streaming and len(response.content) < 200:
            return response

        patch_vary_headers(response, ('Accept-Encoding',))

        # Avoid gzipping if we've already got a content-encoding.
        if response.has_header('Content-Encoding'):
            return response

        # MSIE have issues with gzipped response of various content types.
        if "msie" in request.META.get('HTTP_USER_AGENT', '').lower():
            ctype = response.get('Content-Type', '').lower()
            if not ctype.startswith("text/") or "javascript" in ctype:
                return response

        ae = request.META.get('HTTP_ACCEPT_ENCODING', '')
        if not re_accepts_gzip.search(ae):
            return response

        if response.streaming:
            # Delete the `Content-Length` header for streaming content, because
            # we won't know the compressed size until we stream it.
            response.streaming_content = compress_sequence(response.streaming_content)
            del response['Content-Length']
        else:
            # Return the compressed content only if it's actually shorter.
            compressed_content = compress_string(response.content)
            if len(compressed_content) >= len(response.content):
                return response
            response.content = compressed_content
            response['Content-Length'] = str(len(response.content))

        if response.has_header('ETag'):
            response['ETag'] = re.sub('"$', ';gzip"', response['ETag'])
        response['Content-Encoding'] = 'gzip'

        return response


class UnzipRequestMiddleware(object):
    """
    This middleware decompresses POSTed data if the request contains the
    `Content-Encoding` header with the `gzip` value.
    """
    def process_request(self, request):
        encoding = request.META.get('HTTP_CONTENT_ENCODING', None)
        if encoding == 'gzip':
            data = request._stream.read()
            try:
                d = zlib.decompressobj()
                #  limits the amount of uncompressed data to UNZIP_MAX_SIZE
                uncompressed = d.decompress(data, settings.UNZIP_MAX_SIZE)
                if d.unconsumed_tail:
                    logger.warning('Unzipped file is too large: %s', request.path,
                                   extra={
                                       'status_code': 400,
                                       'request': request
                                   }
                               )
                    return http.HttpResponseBadRequest('<h1>Unzipped file is too large</h1>')
                request._stream = LimitedStream(StringIO(uncompressed), len(uncompressed))
                del request.META['HTTP_CONTENT_ENCODING']
            except zlib.error:
                request._stream = LimitedStream(StringIO(data), len(data))            

        return
