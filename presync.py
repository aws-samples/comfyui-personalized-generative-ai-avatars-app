#!/usr/bin/env python3

import os
import sys
import hashlib
import boto3
import requests
from urllib.parse import urlparse
import shutil
from botocore.exceptions import ClientError
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Global Variables
LOCAL_MODEL_DIR = "./models"
DOWNLOAD_LIST_FILE = "model_list.txt"

def get_unique_suffix():
    session = boto3.Session()
    sts_client = session.client('sts')
    account_id = sts_client.get_caller_identity().get('Account')
    region = session.region_name

    print(f"account_id: {account_id}")
    print(f"region: {region}")

    if not account_id or not region:
        print("Unable to get AWS account ID or region. Please configure AWS CLI or set AWS credentials.")
        sys.exit(1)

    unique_input = f"{account_id}-{region}"
    unique_hash = hashlib.sha256(unique_input.encode('utf-8')).hexdigest()[:10]
    suffix = unique_hash.lower()
    return suffix, region

def ensure_bucket_exists(s3_client, bucket_name, region):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"Bucket {bucket_name} already exists.")
    except ClientError as e:
        error_code = int(e.response['ResponseMetadata']['HTTPStatusCode'])
        if error_code == 404:
            if region == 'us-east-1':
                s3_client.create_bucket(
                    Bucket=bucket_name
                )
            else:
                s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': region}
                )
            print(f"Bucket {bucket_name} created successfully.")
            print(f"Execute now: export MODEL_BUCKET_NAME={bucket_name}")
        elif error_code == 301:
            print(f"Bucket {bucket_name} exists but is in a different region.")
            sys.exit(1)
        elif error_code == 403:
            print(f"Access denied to bucket {bucket_name}. It may exist in another account.")
            sys.exit(1)
        else:
            print(f"Unexpected error (HTTP {error_code}): {e}")
            sys.exit(1)

def download_file(url, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if not os.path.exists(output_path):
        print(f"Downloading {output_path}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        with open(output_path, 'wb') as f, tqdm(
            desc=output_path,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    size = f.write(chunk)
                    bar.update(size)
    else:
        print(f"File {output_path} already exists. Skipping download.")

def read_download_list(file_path):
    if not os.path.isfile(file_path):
        print(f"Error: {file_path} file not found!")
        sys.exit(1)
    download_list = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    url, output_path = parts
                    download_list.append((url.strip(), output_path.strip()))
                else:
                    print(f"Invalid line in {file_path}: {line}")
    return download_list

def upload_file_to_s3_if_not_exists(s3_client, file_path, bucket_name, s3_key):
    try:
        # Check if the object already exists
        s3_client.head_object(Bucket=bucket_name, Key=s3_key)
        print(f"File s3://{bucket_name}/{s3_key} already exists. Skipping upload.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            # Object does not exist, proceed to upload
            try:
                s3_client.upload_file(file_path, bucket_name, s3_key)
                print(f"Uploaded {file_path} to s3://{bucket_name}/{s3_key}")
            except ClientError as upload_error:
                print(f"Failed to upload {file_path} to s3://{bucket_name}/{s3_key}")
                print(upload_error)
                sys.exit(1)
        else:
            print(f"Error checking existence of s3://{bucket_name}/{s3_key}")
            print(e)
            sys.exit(1)

def sync_directory_to_s3(s3_client, local_dir, bucket_name, s3_prefix=''):
    for root, dirs, files in os.walk(local_dir):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_dir)
            s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")
            upload_file_to_s3_if_not_exists(s3_client, local_path, bucket_name, s3_key)

def main():
    suffix, region = get_unique_suffix()
    s3_bucket_name = f"comfyui-models-{suffix}"

    s3_client = boto3.client('s3', region_name=region)
    ensure_bucket_exists(s3_client, s3_bucket_name, region)

    os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)

    download_list = read_download_list(DOWNLOAD_LIST_FILE)

    # Parallel download
    print("### Downloading models in parallel...")
    max_workers = min(8, os.cpu_count() or 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for url, output_path in download_list:
            full_output_path = os.path.join(LOCAL_MODEL_DIR, output_path)
            futures.append(executor.submit(download_file, url, full_output_path))
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error during download: {e}")
                sys.exit(1)

    print(f"### Uploading models to S3 bucket: s3://{s3_bucket_name}/")
    sync_directory_to_s3(s3_client, LOCAL_MODEL_DIR, s3_bucket_name)

    # Uncomment the next two lines if you want to delete local models after upload
    # print("### Cleaning up local models...")
    # shutil.rmtree(LOCAL_MODEL_DIR)

    print(f"### Models have been uploaded to S3 bucket: s3://{s3_bucket_name}/")

if __name__ == "__main__":
    main()
