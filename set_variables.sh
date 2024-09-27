export AWS_DEFAULT_ACCOUNT=<your-account> # e.g. "123456789012"
export AWS_DEFAULT_REGION=<your-region> # e.g. "us-east-1"

export CERTIFICATE_ARN=<your-arn> # e.g. "arn:aws:acm:us-east-1:123456789012:certificate/1234ab1a-1234-1ab2-aa1b-01aa23b4c567"
export CLOUDFRONT_PREFIX_LIST_ID=<your-list> # e.g. "pl-3b927c52" for us-east-1
export HOSTED_ZONE_ID=<your-list> # e.g. "/hostedzone/A12345678AB9C0DE1FGHI"
export ZONE_NAME=<your-domain> # e.g. "example.com"
export RECORD_NAME_COMFYUI=<your-subdomain1> # e.g. "comfyui.${ZONE_NAME}"
# following variables needs only to be set if you choose DeploymentType ComfyUIWithAvatarApp / FullStack
export RECORD_NAME_AVATAR_APP=<your-subdomain2> # e.g. "avatar-app.${ZONE_NAME}"
export RECORD_NAME_AVATAR_GALLERY=<your-subdomain2> # e.g. "avatar-gallery.${ZONE_NAME}"

# following variable is the S3 bucket which is having all models pre-synced to be used during startup
export MODEL_BUCKET_NAME=<comfyui-models-youruniqueid>