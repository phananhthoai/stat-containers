FROM bitnami/python:3.10.12

COPY requirements.txt main.py ./
RUN pip3 install -r requirements.txt

ENTRYPOINT [ "python3", "main.py" ]
