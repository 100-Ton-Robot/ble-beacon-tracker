# openEMS (FDTD solver) + its Python bindings, built from the official source, for sector_model.py.
#
#   docker build -t bletracker-openems rf_model
#   docker run --rm -v "<project folder>:/work" -w /work/rf_model bletracker-openems \
#       python3 sector_model.py --antenna monopole --coarse
#
# No GUI (AppCSXCAD) is built: look at model.xml on a machine with openEMS's GUI if you need to.
FROM debian:trixie-slim

ARG OPENEMS_TAG=v0.37.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
        libhdf5-dev libvtk9-dev libboost-all-dev libcgal-dev libtinyxml-dev \
        python3-dev python3-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recursive --depth 1 --branch ${OPENEMS_TAG} --shallow-submodules \
        https://github.com/thliebig/openEMS-Project.git /src/openEMS-Project \
    && cd /src/openEMS-Project \
    && ./update_openEMS.sh /opt/openEMS --python --disable-GUI --python-venv-dir=/opt/venv \
    ; status=$?; if [ $status -ne 0 ]; then cat /src/openEMS-Project/*.log 2>/dev/null | tail -80; exit $status; fi

ENV PATH=/opt/venv/bin:/opt/openEMS/bin:$PATH \
    LD_LIBRARY_PATH=/opt/openEMS/lib \
    MPLBACKEND=Agg

RUN pip install --no-cache-dir matplotlib h5py numpy \
    && python3 -c "import openEMS, CSXCAD; print('openEMS', openEMS.__file__)"

WORKDIR /work
