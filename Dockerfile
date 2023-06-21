# Use Python 3.9 as base image
FROM python:3.9

# Install python library
RUN pip install azure.storage.blob
RUN pip install azure-servicebus

# Copy program file to container
COPY receive.py .
# COPY 2.7gb.data .

# Run program
CMD ["python", "-u" ,"receive.py"]