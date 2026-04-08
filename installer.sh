#!/bin/bash

currentDIR="$( pwd )"




homeDIR=$currentDIR
echo "Installation will take place in $homeDIR"

echo "[Checking system dependencies]"
PKG_OK=$(dpkg-query -W -f='${Status}' autoconf 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "autoconf not found. Install it with sudo apt-get install autoconf."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' libtool 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "libtool not found. Install it with sudo apt-get install libtool."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' gzip 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "gzip not found. Install it with sudo apt-get install gzip."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' bzr 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "bzr not found. Install it with sudo apt-get install bzr."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' form 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "form not found. Install it with sudo apt-get install form."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' sqlite3 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "sqlite3 not found. Install it with sudo apt-get install sqlite3."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' cython3 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "cython3 not found. Install it with sudo apt-get install cython3."
  exit
fi
PKG_OK=$(dpkg-query -W -f='${Status}' autoconf --version 2>/dev/null | grep -c "ok installed")
if test $PKG_OK = "0" ; then
  echo "autoconf not found. Install it with sudo apt-get install autotools-dev."
  exit
fi

cd $homeDIR

madgraph="MG5_aMC_v3.7.0.tar.gz"
URL=https://launchpad.net/mg5amcnlo/3.0/3.6.x/+download/$madgraph
echo -n "Install MadGraph (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	mkdir MG5;
	echo "[installer] getting MadGraph5"; wget $URL 2>/dev/null || curl -O $URL; 
	tar -zxf $madgraph -C MG5 --strip-components 1;
fi

#Get HepMC tarball
hepmc="hepmc2.06.11.tgz"
echo -n "Install HepMC2 (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	mkdir hepMC_tmp
	URL=http://hepmc.web.cern.ch/hepmc/releases/$hepmc
	echo "[installer] getting HepMC"; wget $URL 2>/dev/null || curl -O $URL; tar -zxf $hepmc -C hepMC_tmp;
	mkdir HepMC-2.06.11; mkdir HepMC-2.06.11/build; mkdir HepMC2;
	echo "Installing HepMC in ./HepMC";
	cd HepMC-2.06.11/build;
	../../hepMC_tmp/HepMC-2.06.11/configure --prefix=$homeDIR/HepMC2 --with-momentum=GEV --with-length=MM;
	make;
	make check;
	make install;

	#Clean up
	cd $homeDIR;
	rm -rf hepMC_tmp; rm $hepmc; rm -rf HepMC-2.06.11;
fi



#Get pythia tarball
pythia="pythia8245.tgz"
URL=https://pythia.org/download/pythia82/$pythia
echo -n "Install Pythia (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	if hash gzip 2>/dev/null; then
		mkdir pythia8;
		echo "[installer] getting Pythia"; wget $URL 2>/dev/null || curl -O $URL; tar -zxf $pythia -C pythia8 --strip-components 1;
		echo "Installing Pythia in pythia8";
		cd pythia8;
		./configure --with-hepmc2=$homeDIR/HepMC2 --with-root=$ROOTSYS --prefix=$homeDIR/pythia8 --with-gzip
		make -j4; make install;
		cd $homeDIR
		rm $pythia;
	else
		echo "[installer] gzip is required. Try to install it with sudo apt-get install gzip";
	fi
fi


fastjet="fastjet-3.4.0.tar.gz"
URL=http://fastjet.fr/repo/$fastjet
echo -n "Install Fastjet (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
	mkdir fastjet_build;
	mkdir fastjet;
	echo "[installer] getting FastJet"; wget $URL 2>/dev/null || curl -O $URL; tar -zxf $fastjet -C fastjet_build --strip-components 1;
	echo "Installing FastJet in fastjet";
	cd fastjet_build;
	./configure --prefix=$homeDIR/fastjet;
	make; make install;
	cd $homeDIR;
	rm -r fastjet_build;
	rm $fastjet;	
fi


echo -n "Install Delphes (y/n)? "
repo=https://github.com/delphes/delphes
URL=http://cp3.irmp.ucl.ac.be/downloads/$delphes
read answer
if echo "$answer" | grep -iq "^y" ;then
  latest=`git ls-remote --sort="version:refname" --tags $repo  | grep -v -e "pre" | grep -v -e "\{\}" | cut -d/ -f3- | tail -n1`
  echo "[installer] Cloning Delphes version $latest";
  git clone --branch $latest https://github.com/delphes/delphes.git Delphes
  cd Delphes;
  export PYTHIA8=$homeDIR/pythia8;
  echo "[installer] installing Delphes";
  make HAS_PYTHIA8=true;
  rm -rf .git
  cd $homeDIR;
fi

echo -n "Install CheckMATE (y/n)? "
read answer
if echo "$answer" | grep -iq "^y" ;then
  echo "[installer] getting CheckMATE";
  git clone git@github.com:CheckMATE2/checkmate2.git CheckMATE
  cd CheckMATE
  latest=`git ls-remote --tags  --sort=committerdate | cut -d/ -f3- | tail -n1`
  cd $homeDIR
  rm -rf CheckMATE
  echo "Cloning version $latest"
  git clone --branch $latest git@github.com:CheckMATE2/checkmate2.git CheckMATE;
  cd CheckMATE;
  alias python=python3
  rm -rf .git
  autoreconf -i -f;
  ./configure --with-rootsys=$ROOTSYS --with-delphes=$homeDIR/Delphes --with-pythia=$homeDIR/pythia8 --with-madgraph=$homeDIR/MG5 --with-hepmc=$homeDIR/HepMC2
  echo "[installer] installing CheckMATE";
  make -j4
  cd $homeDIR
  echo "[installer] Replacing AnalysisHandler.cc with the local version with a fix for muon isolation."
  cp AnalysisHandler.cc ./CheckMATE/tools/fritz/src/analysishandler/AnalysisHandler.cc
fi



cd $currentDIR
