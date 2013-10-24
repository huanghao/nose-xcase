%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%{!?python_version: %define python_version %(%{__python} -c "import sys; sys.stdout.write(sys.version[:3])")}
Name:       itest-core
Summary:    gbs system test automatic script and test cases
Version:    1.3
Release:    1
Group:      Development/Tools
License:    GPLv2
BuildArch:  noarch
URL:        http://www.tizen.org
Source0:    %{name}_%{version}.tar.gz

Requires:   python >= 2.6
%if 0%{?suse_version}
Requires:   python-pexpect
%else
Requires:   pexpect
%endif

%if "%{?python_version}" < "2.7"
Requires:   python-argparse
%endif

BuildRequires: python-setuptools
BuildRequires: python-devel

%description
gbs system test

%prep
%setup -q -n %{name}-%{version}

%install
%{__python} setup.py install --prefix=%{_prefix} --root=%{buildroot}

%files
%defattr(-,root,root,-)
%{python_sitelib}/*
%{_bindir}/runtest
%{_bindir}/imgdiff
