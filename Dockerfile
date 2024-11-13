FROM bitnami/python:3.10.12

#RUN apt update && \
#    apt install -qq -y jq curl iputils-ping net-tools netcat

#RUN mkdir /data

COPY requirements.txt main.py ./
RUN pip3 install -r requirements.txt

ENTRYPOINT [ "python3", "main.py" ]
