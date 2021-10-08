FROM          ubuntu:18.04
MAINTAINER Tom Prince <mozilla@hocat.ca>

# Add worker user
RUN mkdir /builds && \
    useradd -d /builds/worker -s /bin/bash -m worker && \
    mkdir /builds/worker/artifacts && \
    chown worker:worker /builds/worker/artifacts

# %include-run-task

# Add jobgraph package.
# %include requirements/base.txt
ADD topsrcdir/requirements/base.txt /setup/requirements.txt

ADD system-setup.sh /setup/system-setup.sh
RUN bash /setup/system-setup.sh

ENV PATH=/builds/worker/bin:$PATH \
    SHELL=/bin/bash \
    HOME=/builds/worker

# Set a default command useful for debugging
CMD ["/bin/bash", "--login"]
