#!/usr/bin/env python3
import subprocess
import sys
import fileinput
import platform

# START VARIABLES
AD_DOMAIN = input('Active Directory Domain: ')
AD_REALM = input('Active Directory Realm (Usually domain but ALL CAPS): ')
AD_DC_HOSTNAME = input('Domain Controller Hostname (no domain suffix): ')  # no suffix
AD_DC_IP = input('Domain Controller IP: ')
AD_GROUP = input('Domain Group that is allowed to ssh to server: ')
ALLOW_PW_LOGIN = input('Allow password login (y/n): ')
# END VARIABLES

SSSD_CONF = """[sssd]
domains = """ + AD_DOMAIN + """
config_file_version = 2
services = nss, pam, sudo, ssh

[domain/""" + AD_DOMAIN + """]
ad_domain = """ + AD_DOMAIN + """
krb5_realm = """ + AD_REALM + """
realmd_tags = manages-system joined-with-adcli
cache_credentials = True
id_provider = ad
krb5_store_password_if_offline = True
default_shell = /bin/bash
ldap_id_mapping = True
use_fully_qualified_names = True
override_homedir = /home/%u@%d
fallback_homedir = /home/%u@%d
access_provider = ad
ldap_user_extra_attrs = altSecurityIdentities:altSecurityIdentities
ldap_user_ssh_public_key = altSecurityIdentities
ldap_use_tokengroups = True """


def execute_bashcmd(bashCommand):
    process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    sys.stdout.write(output)
    sys.stdout.write(error)

# Check if Linux OS and find Distribution
if platform.system() == "Linux":
    linux_distro = platform.linux_distribution()[0]
    sys.stdout.write("OS found: " + linux_distro + '\n')
else:
    sys.stdout.write("GNU/Linux distribution found: " + linux_distro + '\n')
    sys.exit()


# Install prerequisites based on distribution
if linux_distro == "CentOS Linux":
    sys.stdout.write("No support for CentOS in the current build" + '\n')
    sys.exit()
    execute_bashcmd("yum update")
    execute_bashcmd("yum install -y realmd oddjob oddjob-mkhomedir sssd adcli openldap-clients policycoreutils-python samba-common samba-common-tools krb5-workstation")
elif linux_distro == "Ubuntu":
    execute_bashcmd("apt update")
    execute_bashcmd("apt install -y policykit-1 sssd realmd oddjob oddjob-mkhomedir adcli samba-common")
else:
    sys.stdout.write("GNU/Linux distribution found: " + linux_distro + '\n')

# Set timezone
execute_bashcmd("timedatectl set-timezone Europe/Brussels")

# Add Domain Controllers as DC
DNS = "\n" +AD_DC_IP + " " + AD_DC_HOSTNAME + "." + AD_DOMAIN + " " + AD_DC_HOSTNAME
with open("/etc/hosts", "a") as hosts:
    hosts.write(DNS)

# Add domain to searchable in interface
# TODO: add Centos Support
with fileinput.FileInput("/etc/netplan/50-cloud-init.yaml", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("search: []", "search: \n                - " + AD_DOMAIN + ""), end='')
execute_bashcmd("netplan apply")

# Realm join
execute_bashcmd("realm join -v --user=Administrator --install=/ " + AD_DC_HOSTNAME + "." + AD_DOMAIN)
sys.stdout.write("Server joined the Active Directory Domain: " + AD_DOMAIN + '\n')
execute_bashcmd("realm list")

# SSSD Config
with open("/etc/sssd/sssd.conf", "w") as sssd:
    sssd.write(SSSD_CONF)

with fileinput.FileInput("/etc/pam.d/sshd", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("session [success=ok ignore=ignore module_unknown=ignore default=bad]        pam_selinux.so close", "session required pam_mkhomedir.so skel=/etc/skel/ umask=0022\nsession [success=ok ignore=ignore module_unknown=ignore default=bad]        pam_selinux.so close"), end='')

# Modify SSHD config
sys.stdout.write("Start modifying /etc/ssh/sshd_config" + '\n')

with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("#AuthorizedKeysCommand none", "AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys"), end='')
with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("AuthorizedKeysCommand none", "AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys"), end='')
with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("#AuthorizedKeysCommandUser nobody", "AuthorizedKeysCommandUser root"), end='')
with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("AuthorizedKeysCommandUser nobody", "AuthorizedKeysCommandUser root"), end='')

# Modifying Password login
if (ALLOW_PW_LOGIN == "y" or ALLOW_PW_LOGIN == "yes"):
    with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
        for line in file:
            print(line.replace("#PasswordAuthentication yes", "PasswordAuthentication yes"), end='')
        sys.stdout.write("Password Authentication allowed" + '\n')
else:
    with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
        for line in file:
            print(line.replace("#PasswordAuthentication yes", "PasswordAuthentication no"), end='')
        sys.stdout.write("Password Authentication not allowed" + '\n')

# Security enhancements
with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("#AllowAgentForwarding yes", "AllowAgentForwarding no"), end='')

with fileinput.FileInput("/etc/ssh/sshd_config", inplace=True, backup='.bak') as file:
    for line in file:
        print(line.replace("#AllowTcpForwarding yes", "AllowTcpForwarding no"), end='')

sys.stdout.write("Completed modifying /etc/ssh/sshd_config" + '\n')

# Set login permissions
sys.stdout.write("Start modifying realm permissions" + '\n')
execute_bashcmd("realm deny --all")
execute_bashcmd("realm permit -g "+ AD_GROUP +"@redzone.local")
sys.stdout.write("Completed modifying realm permissions" + '\n')

# Make group sudoers
sys.stdout.write("Start adding AD group to sudoers" + '\n')
sudo = "%" + AD_GROUP +"@" + AD_DOMAIN  + " ALL=(ALL) ALL"
with open("/etc/sudoers", "a") as hosts:
    hosts.write(sudo)
sys.stdout.write("Completed adding AD group to sudoers" + '\n')

sys.stdout.write("Configuration complete, reboot the server" + '\n')
