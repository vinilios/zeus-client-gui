#!/usr/bin/python
# -*- coding: utf-8 -*-

VERSION = "0.1-alpha"

import sys
import os
import json
import copy

from urllib import urlencode, unquote
from urlparse import urlparse, parse_qsl

from zeus.client import get_election_info, do_download_ciphers
from zeus import client
from zeus import core
from PySide import QtGui

from PySide.QtCore import *
from PySide.QtGui import *

CPU_COUNT = 4
try:
    import multiprocessing
    CPU_COUNT = multiprocessing.cpu_count()
except ImportError:
    pass

class Stream(core.TellerStream):
    def __init__(self, reporter, *args, **kwargs):
        self.report = reporter

    def write(self, data):
        self.report(data)
    
    def flush(self):
        pass

class MainWindow(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        self.decrypting = False
        self.keypair_filename = None
        self.trustee_keypair = None
        self.trustee_login_url = None
        self.election_info = None

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.url_label = QLabel("Trustee login url:")

        self.url = QLineEdit()
        self.url.textChanged[str].connect(self.onUrlChange)

        field = QHBoxLayout()
        field.addWidget(self.url_label)
        field.addWidget(self.url)
        layout.addLayout(field)


        self.file_button = QToolButton(text="Select keypair file...")
        self.file_button.clicked.connect(self.onFileButtonClick)
        self.file_label = QLabel("No keypair selected.")

        layout.addWidget(self.file_button)
        layout.addWidget(self.file_label)

        self.decrypt_button = QToolButton(text="Decrypt", )
        self.decrypt_button.setEnabled(False)
        self.decrypt_button.clicked.connect(self.decrypt)
        font = self.decrypt_button.font()
        font.setPointSize(16)
        self.decrypt_button.setFont(font)

        buttonset = QHBoxLayout()
        buttonset.addWidget(self.decrypt_button)

        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status_doc = self.status.document()
        layout.addWidget(self.status)
        layout.addLayout(buttonset)
        version = QLabel("version: %s" % VERSION)
        font = version.font()
        font.setPointSize(9)
        version.setFont(font)
        layout.addWidget(version)
        self.show()
        self.validate()

    def check_gmp(self):
        if core.mpz is None:
            self.report("Warning: Could not import gmpy. Falling back to SLOW crypto.")

    def report(self, msg, type=""):
        msg = msg.strip()
        content = self.status_doc.toPlainText()
        if content and "Computing decryption factors" in content.split("\n")[0].strip():
            content = "\n".join(content.split("\n")[1:])
        content = "{}{}\n".format(type, msg) + content
        self.status_doc.setPlainText(content)
        print msg
        QApplication.processEvents()
        
    def alert(self, msg):
        msgBox = QMessageBox()
        msgBox.setText(str(msg))
        msgBox.exec_()
        print msg

    def decrypt(self):
        if self.decrypting:
            return
        else:
            self.decrypting = True
        teller = core.Teller(outstream=Stream(self.report))
        polls = self.election_info['election']['polls']
        try:
            self.decrypt_button.setEnabled(False)
            self.report("Decrypting...")
            for poll in polls:
                self.report("Downloading poll %r ciphers..." % poll['uuid'])
                conn, headers, base = client.get_login(self.trustee_login_url)
                ciphers_url = urlparse(poll['ciphers_url']).path
                conn.request('GET', ciphers_url, headers=headers)
                response = conn.getresponse()
                if response.status != 200:
                    self.report("Skipping poll %r, received status: %r" % (poll['uuid'], response.status))
                    continue
                save_data = response.read()
                poll['ciphers'] = json.loads(save_data)['tally']

                key = self.trustee_keypair
                secret = int(key['x'])
                pk = key['public_key']
                modulus = int(pk['p'])
                generator = int(pk['g'])
                order = int(pk['q'])
                public = int(pk['y'])
                tally = poll['ciphers']
                ciphers = [(int(ct['alpha']), int(ct['beta']))
                    for ct in tally['tally'][0]]
                self.report("Partially decrypt %d ciphers for poll %r" % (len(ciphers), poll['uuid']))
                factors = core.compute_decryption_factors1(modulus, generator, order,
                                                    secret, ciphers,
                                                    teller=teller)
                decryption_factors = []
                factor_append = decryption_factors.append
                decryption_proofs = []
                proof_append = decryption_proofs.append

                for factor, proof in factors:
                    factor_append(factor)
                    f = {}
                    f['commitment'] = {'A': proof[0], 'B': proof[1]}
                    f['challenge'] = proof[2]
                    f['response'] = proof[3]
                    proof_append(f)

                factors_and_proofs = {
                    'decryption_factors': [decryption_factors],
                    'decryption_proofs': [decryption_proofs]
                }

                self.report("Poll partial decryption completed.")
                self.report("Upload poll %r partial decryptions." % poll['uuid'])

                self.decrypting = False
                path = poll['post_decryption_url']
                path = urlparse(path).path
                conn, headers, redirect = client.get_login(self.trustee_login_url)
                body = urlencode({'factors_and_proofs': json.dumps(factors_and_proofs)})
                headers = copy.copy(headers)
                headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
                conn.request('POST', path, body=body, headers=headers)
                response = conn.getresponse().read()
                self.report("Upload response: %s" % response)

            self.report("Decryption finished.")

        except ValueError, e:
            self.alert(e)
            self.decrypt_button.setEnabled(True)

    def validate(self):
        keypair_file = self.keypair_filename
        login_url = self.trustee_login_url
        self.trustee_keypair = None
        if keypair_file:
            self.file_label.setText(self.keypair_filename)
        if login_url:
            self.url.setText(login_url)

        if keypair_file and login_url:
            with file(keypair_file, 'r') as f:
                try:
                    self.trustee_keypair = json.loads(f.read())
                    self.report("Keypair resolved.")
                except Exception, e:
                    self.alert("Invalid trustee keypair file (%r)." % e)
            try:
                self.election_info = get_election_info(self.trustee_login_url)
                self.report("Election details resolved.")
                url = unquote(self.trustee_login_url)
                parsed = urlparse(url)
                path_parts = parsed.path.split("/")
                _, _, _, _, _, trustee, _ = path_parts[-7:]
                self.url_label.setText("Trustee: %s" % trustee)
                self.report("Election name: %s" % self.election_info['election']['name'])
                self.report("Polls count: %s" % len(self.election_info['election'].get('polls', [])))
            except Exception, e:
                self.url_label.setText("Trustee login url:")
                self.alert("Cannot resolve election info (%r)." % e)

        if self.election_info:
            polls = self.election_info['election'].get('polls', [])
            can_decrypt = True
            for poll in polls:
                if 'ciphers_url' not in poll or 'post_decryption_url' not in poll:
                    self.report("Poll %r is not eligible for decryption." % poll['uuid'])
                    can_decrypt = False
            if can_decrypt:
                self.decrypt_button.setEnabled(True)

    def setKeyPairFile(self, filename):
        self.keypair_filename = filename
        self.validate()

    def onUrlChange(self, text):
        old_url = self.trustee_login_url
        self.trustee_login_url = text.strip()
        if old_url != self.trustee_login_url:
            self.validate()

    def onFileButtonClick(self):
        filename, filter = QtGui.QFileDialog.getOpenFileName(parent=self, caption='Select keypair file', dir='.')
        self.setKeyPairFile(filename)


def main():
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QApplication(sys.argv)
    mw = MainWindow()
    mw.resize(500, 450)
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
