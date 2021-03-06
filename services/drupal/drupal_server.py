# -*- coding: utf-8 -*-
"""A Drupal CMS server based on Python's HTTPServer."""
from __future__ import unicode_literals

import os

from six.moves.socketserver import ThreadingMixIn
from six.moves.BaseHTTPServer import HTTPServer
from six.moves.SimpleHTTPServer import SimpleHTTPRequestHandler
from six.moves.urllib_parse import unquote, urlparse


WEB_PORT = 80
WWW_FOLDER_NAME = "html"
WEB_ALERT_TYPE_NAME = "drupal_rce"
DEFAULT_SERVER_VERSION = "Apache 2"
ALERTS = [WEB_ALERT_TYPE_NAME]


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Extend both classes to have threading capabilities."""


class HoneyHTTPRequestHandler(SimpleHTTPRequestHandler, object):
    """Filter requests to catch Drupalgeddon 2 exploit attempts."""

    def version_string(self):
        """Return the web server name that we run on."""
        return DEFAULT_SERVER_VERSION

    def verify(self, query):
        """Filter HTTP request to make sure it's not an exploit attempt."""
        self.logger.debug("Query: %s", query)
        if query and query.find("&") != -1:
            query_components = {}
            for param in query.split("&"):
                if param.find("=") == -1:
                    continue
                else:
                    key, value = param.split("=")
                    query_components[key] = value

            for component in query_components:
                if component.find("[#") != -1 and len(component) > 1:
                    self.alert(event_name=WEB_ALERT_TYPE_NAME,
                               request=query,
                               orig_ip=self.client_address[0],
                               orig_port=self.client_address[1])
                    break

    def do_GET(self):
        """Handle an HTTP GET request."""
        query = unquote(urlparse(self.path).query)
        self.verify(query)
        super(HoneyHTTPRequestHandler, self).do_GET()

    def do_POST(self):
        """Handle an HTTP POST request."""
        content_length = int(self.headers['Content-Length'])
        post_data = unquote(self.rfile.read(content_length).decode())
        self.verify(post_data)
        super(HoneyHTTPRequestHandler, self).do_GET()

    def log_error(self, message, *args):
        """Log an error."""
        self.log_message("error", message, *args)

    def log_request(self, code="-", size="-"):
        """Log an incoming request."""
        # Due to hilarity involving HTTPServer using "%s"-style formatting to format strings,
        # and the URLs sometimes having extra %'s in them, we have to escape them by making
        # them into %%'s.
        self.log_message("debug", '"{!s}" {!s} {!s}'.format(self.requestline.replace("%", "%%"), code, size))

    def log_message(self, level, message, *args):
        """Send message to logger with standard apache format."""
        try:
            getattr(self.logger, level)
        except AttributeError:
            self.logger.error("Invalid level of debug requested ({}), logging as debug".format(level))
            level = "debug"

        self.logger.debug(message)
        self.logger.debug(str(args))
        getattr(self.logger, level)("{!s} - - [{!s}] {!s}".format(self.client_address[0],
                                                                  self.log_date_time_string(),
                                                                  message % args))


class DrupalServer(object):
    """Drupal CMS honeypot."""

    def __init__(self, logger, alert):
        self.logger = logger
        alerting_client_handler = HoneyHTTPRequestHandler
        alerting_client_handler.logger = logger
        alerting_client_handler.alert = alert
        self.httpd = ThreadingHTTPServer(("", WEB_PORT), alerting_client_handler)

    def start(self):
        """Start serving requests by starting the underlying HTTP server."""
        os.chdir(os.path.join(os.path.dirname(__file__), WWW_FOLDER_NAME))
        self.logger.info("Starting Drupal server on port {port}".format(port=WEB_PORT))
        self.httpd.serve_forever()
        return True

    def stop(self):
        """Stop serving requests."""
        self.logger.info("Shutting down Drupal server...")
        if self.httpd:
            self.httpd.shutdown()
            self.httpd = None
