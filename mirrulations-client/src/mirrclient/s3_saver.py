import os
import json
from dotenv import load_dotenv
import boto3


class S3Saver():

    def __init__(self, bucket_name="mirrulations"):
        self.get_credentials()
        self.access_key = None
        self.secret_access_key = None
        self.s3_client = self.get_s3_client()
        self.bucket_name = bucket_name

    def get_s3_client(self):
        if self.get_credentials() is False:
            print("No credentials provided, Unable to connect to S3")
        return boto3.client(
                's3',
                region_name='us-east-1',
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_access_key
                )

    def get_credentials(self):
        load_dotenv()
        self.access_key = os.getenv("AWS_ACCESS_KEY")
        self.secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        return (self.access_key is not None and
                self.secret_access_key is not None)

    def save_json(self, path, data):
        response = self.s3_client.put_object(
            Bucket=self.bucket_name,
            # Path needs to be data/xxx
            Key=path,
            Body=json.dumps(data)
            )
        print(f"SUCCESS: Wrote json to S3: {path}")
        return response

    def save_binary(self, path, data):
        response = self.s3_client.put_object(
            Bucket=self.bucket_name,
            # Path needs to be data/xxx
            Key=path,
            Body=data)
        print(f"SUCCESS: Wrote binary to S3: {path}")
        return response
