# https://github.com/cdrx/docker-pyinstaller
FROM ubuntu:14.04

ENV DEBIAN_FRONTEND noninteractive

ARG WINE_VERSION=winehq-devel
ARG PYTHON_VERSION=2.7.12
ARG PYINSTALLER_VERSION=3.3

# we need wine for this all to work, so we'll use the PPA
RUN set -x \
    && dpkg --add-architecture i386 \
    && apt-get update -qy \
    && apt-get install --no-install-recommends -qfy software-properties-common \
    && add-apt-repository ppa:wine/wine-builds \
    && apt-get update -qy \
    && apt-get install --no-install-recommends -qfy $WINE_VERSION winetricks wget \
    && apt-get clean

# wine settings
ENV WINEARCH win32
ENV WINEDEBUG fixme-all
ENV WINEPREFIX /wine

# PYPI repository location
ENV PYPI_URL=https://pypi.python.org/
# PYPI index location
ENV PYPI_INDEX_URL=https://pypi.python.org/simple

# install python inside wine
RUN set -x \
    && wget -nv https://www.python.org/ftp/python/$PYTHON_VERSION/python-$PYTHON_VERSION.msi \
    && wine msiexec /qn /a python-$PYTHON_VERSION.msi \
    && rm python-$PYTHON_VERSION.msi \
    && wget -nv https://download.microsoft.com/download/7/9/6/796EF2E4-801B-4FC4-AB28-B59FBF6D907B/VCForPython27.msi \
    && wine msiexec /qn /a VCForPython27.msi \
    && rm VCForPython27.msi \
    && sed -i 's/_windows_cert_stores = .*/_windows_cert_stores = ("ROOT",)/' "/wine/drive_c/Python27/Lib/ssl.py" \
    && echo 'wine '\''C:\Python27\python.exe'\'' "$@"' > /usr/bin/python \
    && echo 'wine '\''C:\Python27\Scripts\easy_install.exe'\'' "$@"' > /usr/bin/easy_install \
    && echo 'wine '\''C:\Python27\Scripts\pip.exe'\'' "$@"' > /usr/bin/pip \
    && echo 'wine '\''C:\Python27\Scripts\pyinstaller.exe'\'' "$@"' > /usr/bin/pyinstaller \
    && chmod +x /usr/bin/* \
    && wget https://bootstrap.pypa.io/ez_setup.py -O - | /usr/bin/python \
    && /usr/bin/easy_install pip \
    && echo 'assoc .py=PythonScript' | wine cmd \
    && echo 'ftype PythonScript=c:\Python27\python.exe "%1" %*' | wine cmd \
    && while pgrep wineserver >/dev/null; do echo "Waiting for wineserver"; sleep 1; done \
    && rm -rf /tmp/.wine-*

# install pyinstaller
RUN /usr/bin/pip install pyinstaller==$PYINSTALLER_VERSION
RUN /usr/bin/pip install PySide
RUN /usr/bin/pip install PyCrypto
RUN /usr/bin/pip install https://files.pythonhosted.org/packages/0b/ab/d029a41085cd9faeef3add2be9542345d74d5603760f3a9f54759483260a/gmpy2-2.0.8-cp27-none-win32.whl

# put the src folder inside wine
RUN mkdir /src/ && ln -s /src /wine/drive_c/src
VOLUME /src/
WORKDIR /wine/drive_c/src/
RUN mkdir -p /wine/drive_c/tmp

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
