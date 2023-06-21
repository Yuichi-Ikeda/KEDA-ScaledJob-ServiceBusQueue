import os
import json
import uuid
from datetime import datetime, timedelta
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.storage.blob import BlobServiceClient, generate_container_sas, ContainerSasPermissions

### Main ###
def main():
    # JOB ID for tracking
    jobID = str(uuid.uuid4())
    print(str(datetime.now()) + '\tjob-id: ' + jobID, flush=True)

    # Generate SAS token for blob container
    sas_url = generateSaSUri(jobID)

    # ServiceBus Queue connection
    conn_str = os.environ.get("SERVICE_BUS_CONNECTION")
    queue_name = os.environ['SERVICE_BUS_QUEUE_NAME']
    queue_client = ServiceBusClient.from_connection_string(conn_str)
    sender = queue_client.get_queue_sender(queue_name)

    # Set number of messages to send
    for num in range(3000):
        task = {
            'job-id': jobID,
            'task-id': num,
            'sas-url': sas_url,
            'wait-seconds': 900
        }
        message = ServiceBusMessage(json.dumps(task))
        sender.send_messages(message)

    queue_client.close()


### Generate SAS token for container ###
def generateSaSUri(jobID):
    try:
        connection_string = os.getenv("STORAGE_CONNECTION")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.create_container(jobID)

        sas_token = generate_container_sas(
            container_client.account_name,
            container_client.container_name,
            account_key=container_client.credential.account_key,
            permission=ContainerSasPermissions(write=True),
            expiry=datetime.utcnow() + timedelta(hours=24),
            start=datetime.utcnow() - timedelta(minutes=1)
        )

        sas_url=f"{container_client.url}/?{sas_token}"
        #print("SAS URL: " + sas_url, flush=True)
        return sas_url
    
    except Exception as ex:
        print("Exception:")
        print(ex)
        return None

### call main function ###
if __name__ == "__main__":
    main()