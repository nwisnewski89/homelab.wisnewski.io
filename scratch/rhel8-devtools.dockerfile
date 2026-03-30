# UBI 8: packages updated/upgraded and a Development-Tools-equivalent toolchain.
#
# Red Hat UBI repos do not ship dnf group definitions, so `dnf groupinstall "Development Tools"`
# is not available. These packages match the usual intent (compile, debug, build RPMs, cmake, git).
# Tools such as flex/bison are not in UBI; add EPEL or install from source if you need them.
#
# Boost: `boost` / `boost-devel` are in full RHEL 8 AppStream but not in the UBI AppStream subset.
# EPEL 8 does not ship them. Rocky Linux 8 AppStream is ABI-compatible with UBI 8 (same .el8 lineage);
# use it only to install Boost, then drop the repo so later `dnf update` stays on UBI.
FROM registry.access.redhat.com/ubi8/ubi:latest

USER root

RUN dnf -y update \
    && dnf -y upgrade \
    && dnf -y install \
        gcc gcc-c++ make \
        autoconf automake libtool \
        binutils \
        pkgconf-pkg-config \
        gdb patch diffutils gettext \
        redhat-rpm-config rpm-build \
        strace cmake git \
    && dnf clean all \
    && rm -rf /var/cache/dnf /var/cache/yum

# Rocky Linux 8 AppStream — https://wiki.rockylinux.org/en/rocky/repo
RUN curl -sL https://download.rockylinux.org/pub/rocky/RPM-GPG-KEY-rockyofficial \
        -o /etc/pki/rpm-gpg/RPM-GPG-KEY-rockyofficial \
    && rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-rockyofficial \
    && printf '%s\n' \
         '[rocky-appstream]' \
         'name=Rocky Linux 8 - AppStream' \
         'baseurl=https://download.rockylinux.org/pub/rocky/8/AppStream/$basearch/os/' \
         'gpgcheck=1' \
         'enabled=1' \
         'gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-rockyofficial' \
         > /etc/yum.repos.d/rocky-appstream.repo \
    && dnf -y install boost boost-devel \
    && rm -f /etc/yum.repos.d/rocky-appstream.repo \
    && dnf clean all \
    && rm -rf /var/cache/dnf /var/cache/yum

CMD ["/bin/bash"]
