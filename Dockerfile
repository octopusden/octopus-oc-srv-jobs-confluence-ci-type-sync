FROM python:3.7

USER root
RUN apt-get --quiet --assume-yes update && apt-get --quiet --assume-yes install sqlite3
RUN rm -rf /build
COPY --chown=root:root . /build
WORKDIR /build
RUN python -m pip install $(pwd) && python -m unittest discover -v && python setup.py bdist_wheel
