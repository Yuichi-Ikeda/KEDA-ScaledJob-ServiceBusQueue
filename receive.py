import os
import json
import time
from datetime import datetime
from azure.servicebus import ServiceBusClient, AutoLockRenewer
from azure.storage.blob import ContainerClient

# ServiceBus Queue connection
conn_str = os.environ['SERVICE_BUS_CONNECTION']
queue_name = os.environ['SERVICE_BUS_QUEUE_NAME']

queue_client = ServiceBusClient.from_connection_string(conn_str)
receiver = queue_client.get_queue_receiver(queue_name)
received_msgs = receiver.receive_messages(max_message_count=1)
msg = received_msgs[0]

# Auto renew lock for 30 minutes
renewer = AutoLockRenewer()
renewer.register(receiver, msg, max_lock_renewal_duration=1800)

task = json.loads(str(msg))
print('TASK_START: {}, job-id: {}, task-id: {}'.format(str(datetime.utcnow()), task['job-id'], task['task-id']), flush=True)

# Wait for seconds for task simulation
time.sleep(task['wait-seconds'])

try:
    # Upload task result to blob storage
    container = ContainerClient.from_container_url(task['sas-url'])
    container.upload_blob(name='task-{:06}'.format(task['task-id']), data='Task Starting.', overwrite=True)
except Exception as ex:
    print('TASK_EXCEPTION: {}, job-id: {}, task-id: {}, ex: {}'.format(str(datetime.utcnow()), task['job-id'], task['task-id'], ex), flush=True)

# Manual ack
receiver.complete_message(msg)
queue_client.close()

print('TASK_END: {}, job-id: {}, task-id: {}'.format(str(datetime.utcnow()), task['job-id'], task['task-id']), flush=True)
