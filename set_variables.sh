export AWS_DEFAULT_ACCOUNT=<your-account> # e.g. "123456789012"
export AWS_DEFAULT_REGION=<your-region> # e.g. "us-east-1"

export CLOUDFRONT_CERTIFICATE_ARN=<your-arn> # e.g. "arn:aws:acm:us-east-1:123456789012:certificate/1234ab1a-1234-1ab2-aa1b-01aa23b4c567"
export ALB_CERTIFICATE_ARN=<your-arn> # e.g. "arn:aws:acm:us-east-1:123456789012:certificate/1234ab1a-1234-1ab2-aa1b-01aa23b4c567"
export CLOUDFRONT_PREFIX_LIST_ID=<your-list> # e.g. "pl-3b927c52" for us-east-1
export HOSTED_ZONE_ID=<your-list> # e.g. "/hostedzone/A12345678AB9C0DE1FGHI"
export ZONE_NAME=<your-domain> # e.g. "example.com"
export RECORD_NAME_COMFYUI=<your-subdomain1> # e.g. "comfyui.${ZONE_NAME}"
# following variables needs only to be set if you choose DeploymentType ComfyUIWithAvatarApp / FullStack
export RECORD_NAME_AVATAR_APP=<your-subdomain2> # e.g. "avatar-app.${ZONE_NAME}"
export RECORD_NAME_AVATAR_GALLERY=<your-subdomain2> # e.g. "avatar-gallery.${ZONE_NAME}"

# MODEL_BUCKET_NAME is set automatically. If you prefer, you can uncomment the next line and define it yourself
# export MODEL_BUCKET_NAME=<your-individual-name>
if [ -z "$MODEL_BUCKET_NAME" ]; then
  # Use the AWS account and region from above
  if [ -n "$AWS_DEFAULT_ACCOUNT" ] && [ -n "$AWS_DEFAULT_REGION" ]; then
    # Generate a unique suffix based on account ID and region
    UNIQUE_INPUT="${AWS_DEFAULT_ACCOUNT}-${AWS_DEFAULT_REGION}"
    # On macOS, use shasum instead of sha256sum
    SUFFIX=$(echo -n "$UNIQUE_INPUT" | shasum -a 256 | cut -c1-10)
    export MODEL_BUCKET_NAME="comfyui-models-${SUFFIX}"
    echo "MODEL_BUCKET_NAME automatically set to: $MODEL_BUCKET_NAME"
    echo "This bucket will be used for storing and retrieving models."
  else
    echo "ERROR: Cannot auto-generate MODEL_BUCKET_NAME because AWS_DEFAULT_ACCOUNT or AWS_DEFAULT_REGION is not set"
    echo "Please set AWS_DEFAULT_ACCOUNT and AWS_DEFAULT_REGION at the top of this file."
    echo "Example:"
    echo "  export AWS_DEFAULT_ACCOUNT=123456789012"
    echo "  export AWS_DEFAULT_REGION=us-east-1"
    # Don't exit here as the user might be editing the file
  fi
else
  echo "Using existing MODEL_BUCKET_NAME: $MODEL_BUCKET_NAME"
fi