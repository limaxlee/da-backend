FROM docker-remote.bart.sec.samsung.net/python:3.13.13

COPY ./da-backend /home/work/da-backend
COPY ./config.yaml /home/work/da-backend/config.yaml

WORKDIR /home/work/da-backend
RUN python -m pip install -r requirements_py313_prod.txt --no-cache-dir

EXPOSE 9999

CMD ["python", "-m", "data_agent", "-c", "/home/work/da-backend/config.yaml"]
