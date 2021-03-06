#!/usr/bin/env python

# Unix SMB/CIFS implementation.
# A test for the ntlm_auth tool
# Copyright (C) Kai Blin <kai@samba.org> 2008
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""Test ntlm_auth
This test program will start ntlm_auth with the given command line switches and
see if it will get the expected results.
"""

import os
import sys
from optparse import OptionParser


class ReadChildError(Exception):
    pass


class WriteChildError(Exception):
    pass


def readLine(pipe):
    """readLine(pipe) -> str
    Read a line from the child's pipe, returns the string read.
    Throws ReadChildError if the read fails.
    """
    newline = -1
    buf = b""
    while newline == -1:
        more = os.read(pipe, 2047)
        buf = buf + more
        newline = buf.find(b'\n')
        if more == b"":
            raise ReadChildError()

    return buf[:newline]


def writeLine(pipe, buf):
    """writeLine(pipe, buf) -> nul
    Write a line to the child's pipe.
    Raises WriteChildError if the write fails.
    """
    written = os.write(pipe, buf)
    if written != len(buf):
        raise WriteChildError()
    os.write(pipe, b"\n")


def parseCommandLine():
    """parseCommandLine() -> (opts, ntlm_auth_path)
    Parse the command line.
    Return a tuple consisting of the options and the path to ntlm_auth.
    """
    usage = "usage: %prog [options] path/to/ntlm_auth"
    parser = OptionParser(usage)

    parser.set_defaults(client_username="foo")
    parser.set_defaults(client_password="secret")
    parser.set_defaults(client_domain="FOO")
    parser.set_defaults(client_helper="ntlmssp-client-1")

    parser.set_defaults(server_username="foo")
    parser.set_defaults(server_password="secret")
    parser.set_defaults(server_domain="FOO")
    parser.set_defaults(server_helper="squid-2.5-ntlmssp")
    parser.set_defaults(config_file="/etc/samba/smb.conf")

    parser.add_option("--client-username", dest="client_username",
                      help="User name for the client. [default: foo]")
    parser.add_option("--client-password", dest="client_password",
                      help="Password the client will send. [default: secret]")
    parser.add_option("--client-domain", dest="client_domain",
                      help="Domain the client authenticates for. [default: FOO]")
    parser.add_option("--client-helper", dest="client_helper",
                      help="Helper mode for the ntlm_auth client. [default: ntlmssp-client-1]")
    parser.add_option("--client-use-cached-creds", dest="client_use_cached_creds",
                      help="Use winbindd credentials cache (rather than default username/pw)", action="store_true")

    parser.add_option("--target-hostname", dest="target_hostname",
                      help="Target hostname for kerberos")
    parser.add_option("--target-service", dest="target_service",
                      help="Target service for kerberos")

    parser.add_option("--server-username", dest="server_username",
                      help="User name server uses for local auth. [default: foo]")
    parser.add_option("--server-password", dest="server_password",
                      help="Password server uses for local auth. [default: secret]")
    parser.add_option("--server-domain", dest="server_domain",
                      help="Domain server uses for local auth. [default: FOO]")
    parser.add_option("--server-helper", dest="server_helper",
                      help="Helper mode for the ntlm_auth server. [default: squid-2.5-server]")
    parser.add_option("--server-use-winbindd", dest="server_use_winbindd",
                      help="Use winbindd to check the password (rather than default username/pw)", action="store_true")
    parser.add_option("--require-membership-of", dest="sid",
                      help="Require that the user is a member of this group to authenticate.")

    parser.add_option("-s", "--configfile", dest="config_file",
                      help="Path to smb.conf file. [default:/etc/samba/smb.conf")

    (opts, args) = parser.parse_args()
    if len(args) != 1:
        parser.error("Invalid number of arguments.")

    if not os.access(args[0], os.X_OK):
        parser.error("%s is not executable." % args[0])

    return (opts, args[0])


def main():
    """main() -> int
    Run the test.
    Returns 0 if test succeeded, <>0 otherwise.
    """
    (opts, ntlm_auth_path) = parseCommandLine()

    (client_in_r, client_in_w) = os.pipe()
    (client_out_r, client_out_w) = os.pipe()

    client_pid = os.fork()

    if not client_pid:
        # We're in the client child
        os.close(0)
        os.close(1)

        os.dup2(client_out_r, 0)
        os.close(client_out_r)
        os.close(client_out_w)

        os.dup2(client_in_w, 1)
        os.close(client_in_r)
        os.close(client_in_w)

        client_args = []
        client_args.append("--helper-protocol=%s" % opts.client_helper)
        client_args.append("--username=%s" % opts.client_username)
        if opts.client_use_cached_creds:
            client_args.append("--use-cached-creds")
        else:
            client_args.append("--password=%s" % opts.client_password)
        client_args.append("--domain=%s" % opts.client_domain)
        client_args.append("--configfile=%s" % opts.config_file)
        if opts.target_service:
            client_args.append("--target-service=%s" % opts.target_service)
        if opts.target_hostname:
            client_args.append("--target-hostname=%s" % opts.target_hostname)

        os.execv(ntlm_auth_path, client_args)

    client_in = client_in_r
    os.close(client_in_w)

    client_out = client_out_w
    os.close(client_out_r)

    (server_in_r, server_in_w) = os.pipe()
    (server_out_r, server_out_w) = os.pipe()

    server_pid = os.fork()

    if not server_pid:
        # We're in the server child
        os.close(0)
        os.close(1)

        os.dup2(server_out_r, 0)
        os.close(server_out_r)
        os.close(server_out_w)

        os.dup2(server_in_w, 1)
        os.close(server_in_r)
        os.close(server_in_w)

        server_args = []
        server_args.append("--helper-protocol=%s" % opts.server_helper)
        if not opts.server_use_winbindd:
            server_args.append("--username=%s" % opts.server_username)
            server_args.append("--password=%s" % opts.server_password)
            server_args.append("--domain=%s" % opts.server_domain)
            if opts.sid:
                raise Exception("Server must be using winbindd for require-membership-of.")
        else:
            if opts.sid:
                server_args.append("--require-membership-of=%s" % opts.sid)

        server_args.append("--configfile=%s" % opts.config_file)

        os.execv(ntlm_auth_path, server_args)

    server_in = server_in_r
    os.close(server_in_w)

    server_out = server_out_w
    os.close(server_out_r)

    if opts.client_helper == "ntlmssp-client-1" and opts.server_helper == "squid-2.5-ntlmssp":

        # We're in the parent
        writeLine(client_out, b"YR")
        buf = readLine(client_in)
        if buf.count(b"YR ", 0, 3) != 1:
            sys.exit(1)

        writeLine(server_out, buf)
        buf = readLine(server_in)

        if buf.count(b"TT ", 0, 3) != 1:
            sys.exit(2)

        writeLine(client_out, buf)
        buf = readLine(client_in)

        if buf.count(b"AF ", 0, 3) != 1:
            sys.exit(3)

        # Client sends 'AF <base64 blob>' but server expects 'KK <abse64 blob>'
        buf = buf.replace(b"AF", b"KK", 1)

        writeLine(server_out, buf)
        buf = readLine(server_in)

        if buf.count(b"AF ", 0, 3) != 1:
            sys.exit(4)

    elif opts.client_helper == "ntlmssp-client-1" and opts.server_helper == "gss-spnego":
        # We're in the parent
        writeLine(client_out, b"YR")
        buf = readLine(client_in)

        if buf.count(b"YR ", 0, 3) != 1:
            sys.exit(1)

        writeLine(server_out, buf)
        buf = readLine(server_in)

        if buf.count(b"TT ", 0, 3) != 1:
            sys.exit(2)

        writeLine(client_out, buf)
        buf = readLine(client_in)

        if buf.count(b"AF ", 0, 3) != 1:
            sys.exit(3)

        # Client sends 'AF <base64 blob>' but server expects 'KK <abse64 blob>'
        buf = buf.replace(b"AF", b"KK", 1)

        writeLine(server_out, buf)
        buf = readLine(server_in)

        if buf.count(b"AF * ", 0, 5) != 1:
            sys.exit(4)

    elif opts.client_helper == "gss-spnego-client" and opts.server_helper == "gss-spnego":
        # We're in the parent
        writeLine(server_out, b"YR")
        buf = readLine(server_in)

        while True:
            if buf.count(b"AF ", 0, 3) != 1 and buf.count(b"TT ", 0, 3) != 1:
                sys.exit(1)

            writeLine(client_out, buf)
            buf = readLine(client_in)

            if buf.count(b"AF", 0, 2) == 1:
                break

            if buf.count(b"AF ", 0, 5) != 1 and buf.count(b"KK ", 0, 3) != 1 and buf.count(b"TT ", 0, 3) != 1:
                sys.exit(2)

            writeLine(server_out, buf)
            buf = readLine(server_in)

            if buf.count(b"AF * ", 0, 5) == 1:
                break

    else:
        sys.exit(5)

    if opts.client_helper == "ntlmssp-client-1":
        writeLine(client_out, b"GK")
        buf = readLine(client_in)

        if buf.count(b"GK ", 0, 3) != 1:
            sys.exit(4)

        writeLine(client_out, b"GF")
        buf = readLine(client_in)

        if buf.count(b"GF ", 0, 3) != 1:
            sys.exit(4)

    if opts.server_helper == "squid-2.5-ntlmssp":
        writeLine(server_out, b"GK")
        buf = readLine(server_in)

        if buf.count(b"GK ", 0, 3) != 1:
            sys.exit(4)

        writeLine(server_out, b"GF")
        buf = readLine(server_in)

        if buf.count(b"GF ", 0, 3) != 1:
            sys.exit(4)

    os.close(server_in)
    os.close(server_out)
    os.close(client_in)
    os.close(client_out)
    os.waitpid(server_pid, 0)
    os.waitpid(client_pid, 0)
    sys.exit(0)


if __name__ == "__main__":
    main()
