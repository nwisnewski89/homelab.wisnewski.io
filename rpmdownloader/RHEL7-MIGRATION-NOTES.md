# RHEL 7 Equivalent RPMs (from UBI 8 list)

## How to get EL7 equivalents

### Option 1: Use the package list with yum on RHEL 7 / UBI 7

On any RHEL 7 system or inside a `ubi7/ubi` container:

```bash
yum install -y \
  annobin automake dracut gcc gcc-c++ gcc-gdb-plugin \
  grub2-common grub2-tools grub2-tools-minimal grubby hardlink intltool jq \
  kbd kbd-legacy kbd-misc kmod kpartx libgomp libkcapi libkcapi-hmaccalc \
  libpeas libquadmath-devel libtool memstrack ncurses-devel net-tools \
  nmap-ncat oniguruma os-prober patchutils perl perl-Encode perl-generators \
  perl-interpreter perl-libs perl-Sys-Syslog perl-Time-HiRes pigz procps-ng \
  rpm rpm-build-libs rpm-libs rpm-sign systemd-udev systemtap systemtap-client \
  valgrind valgrind-devel
```

### Option 2: Download RPMs and produce a tar for Nexus (UBI 7 and UBI 8)

The same Dockerfile and **package list** (`package-list.txt`) work for both UBI 7 and UBI 8. The Dockerfile detects the base image and uses `yum`/`yumdownloader` for UBI 7 and `dnf`/`dnf download` for UBI 8.

**Build UBI 7 tar:**

```bash
docker build -f Dockerfile.rhel7-deps \
  --build-arg BASE_IMAGE=registry.access.redhat.com/ubi7/ubi \
  --build-arg VARIANT=el7 \
  -t rpms-tar:el7 .
```

**Build UBI 8 tar:**

```bash
docker build -f Dockerfile.rhel7-deps \
  --build-arg BASE_IMAGE=registry.access.redhat.com/ubi8/ubi \
  --build-arg VARIANT=el8 \
  -t rpms-tar:el8 .
```

**Extract the tar to the host:**

```bash
# UBI 7
docker run --rm rpms-tar:el7 cat /output/rpm-deps-el7.tar > rpm-deps-el7.tar
# UBI 8
docker run --rm rpms-tar:el8 cat /output/rpm-deps-el8.tar > rpm-deps-el8.tar
```

**Optional:** Use a different package list file: `--build-arg PACKAGE_LIST=rhel7-package-list.txt`

**Upload to Nexus (raw/hosted repo):**

- **Raw (generic file):** Upload `rpm-deps-el7.tar` or `rpm-deps-el8.tar` to a raw repository.
- **RPM repo:** Untar and upload the `.rpm` files into a Nexus yum hosted repository:
  ```bash
  mkdir rpms && tar -xvf rpm-deps-el7.tar -C rpms
  # Then use Nexus UI "Upload" or API for each RPM
  ```

### Option 3: Build a UBI 7 image that installs the RPMs

```bash
# Use a separate Dockerfile that runs yum install -y <packages> (see package list)
docker build -f Dockerfile.rhel7-install -t myapp:rhel7 .
```

### Option 4: Generate package names from any EL8 RPM list

To turn a list of `name-version-release.arch.rpm` lines into just names:

```bash
sed -E 's/-[0-9].*\.(x86_64|noarch)\.rpm$//' your-el8-rpm-list.txt | sort -u
```

---

## Package-by-package notes (RHEL 7 vs 8)

| Package       | RHEL 7 note |
|---------------|--------------|
| **annobin**   | In EPEL 7 as `annobin`. Enable EPEL: `yum install -y epel-release` then install. Or use Developer Toolset if you need annocheck. |
| **microdnf**  | **Omitted** – RHEL 7 minimal images use it, but the full `ubi7/ubi` uses **yum**. If you need a minimal image, use `ubi7/ubi-minimal` (it has microdnf); then install the rest with `microdnf install ...`. |
| **perl-\***   | Same names on EL7; versions will be older (e.g. perl 5.16 on EL7 vs 5.26 on EL8). |
| **gcc / gcc-c++** | EL7 ships older gcc (e.g. 4.8). For gcc 8+ on EL7 use **Red Hat Developer Toolset**: `yum install -y gcc-toolset-8-gcc gcc-toolset-8-gcc-c++` and run via `scl enable gcc-toolset-8 bash`. |
| **memstrack** | Available in standard RHEL 7 repos. |
| **systemtap** | Available; may need `kernel-devel` for some probes. |

---

## If something fails to install

1. **Enable EPEL 7** (for annobin and other extras):
   ```bash
   yum install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-7.noarch.rpm
   ```

2. **Find which repo provides a package** (on a RHEL 7 system):
   ```bash
   yum provides <package-name>
   ```

3. **Check package name differences**: A few packages were renamed or split between EL7 and EL8. If a name fails, try:
   ```bash
   yum search <partial-name>
   ```

---

## One-liner to install from file

If you use `rhel7-package-list.txt` (one package per line, comments with `#`):

```bash
yum install -y $(grep -v '^#' rhel7-package-list.txt | grep -v '^$' | tr '\n' ' ')
```
