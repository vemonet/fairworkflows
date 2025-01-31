import base64
import cgi
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List

from jinja2 import Environment, PackageLoader, select_autoescape

from fairworkflows.config import MANUAL_ASSISTANT_HOST, MANUAL_ASSISTANT_PORT

logging.basicConfig(level=logging.INFO)
env = Environment(loader=PackageLoader('fairworkflows', 'templates'), autoescape=select_autoescape('html'))

ENCODING = 'UTF-8'


def _render_manual_step(step):
    template = env.get_template('manualstep.html')
    return template.render(step=step, outputs=_outputs_to_html(step.outputs)).encode(ENCODING)


def _outputs_to_html(outputs):
    """
    Extract the information necessary to render the outputs in an html form.
    :param outputs:
    :return:
    """

    for o in outputs:
        yield base64.b64encode(o.name.encode()).decode(), o.name, o.computational_type


def _create_request_handler(step):
    class ManualStepRequestHandler(BaseHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            self.step = step
            super().__init__(request, client_address, server)

        def _set_response(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

        def do_GET(self):
            self._set_response()
            self.wfile.write(_render_manual_step(self.step))

        def do_POST(self):
            # Parse the form data posted
            form_data = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    'REQUEST_METHOD': 'POST',
                    'CONTENT_TYPE': self.headers['Content-Type'],
                }
            )

            # Assuming all ids are unique
            form_data = {field.name: field.value for field in form_data.list}

            if _all_boxes_checked(form_data, step.outputs):
                self.server.confirm_output(form_data)
            else:
                # Just display the page again
                self.do_GET()

    return ManualStepRequestHandler


def _all_boxes_checked(form_data: Dict[str, List[str]], outputs):
    return len(form_data.keys()) == len(outputs)


class ManualTaskServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.done = False
        self.outputs = []

    def confirm_output(self, outputs):
        self.outputs = {base64.b64decode(k).decode(): bool(v) for k, v in outputs.items()}
        self.done = True

    def is_done(self):
        return self.done


def execute_manual_step(step):
    server_address = (MANUAL_ASSISTANT_HOST, MANUAL_ASSISTANT_PORT)
    server = ManualTaskServer(server_address, _create_request_handler(step))

    logging.info('Starting Manual Step Assistant')
    logging.info(f'Please go to http://{MANUAL_ASSISTANT_HOST}:{MANUAL_ASSISTANT_PORT} to perform the manual step')

    try:
        while not server.is_done():
            server.handle_request()

        logging.info('Manual step has been completed.')
        return server.outputs
    finally:
        server.server_close()
