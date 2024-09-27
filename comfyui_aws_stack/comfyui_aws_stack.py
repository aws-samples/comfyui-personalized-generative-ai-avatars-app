from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_logs as logs,
    aws_s3 as s3,
    aws_iam as iam,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_actions as elb_actions,
    aws_elasticloadbalancingv2_targets as targets,
    aws_events as events,
    aws_events_targets as event_targets,
    Stack,
    aws_cloudwatch as cloudwatch,
    Duration,
    RemovalPolicy,
    aws_lambda as lambda_,
    aws_cognito as cognito,
    aws_servicediscovery as sd,
    aws_autoscaling_hooktargets as hooktargets,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_certificatemanager as acm,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
    aws_secretsmanager as secretsmanager, SecretValue,
    aws_cloudtrail as cloudtrail,
    aws_efs as efs
    )
from cdk_nag import NagSuppressions
from constructs import Construct
import os, hashlib
import urllib.parse

"""
ComfyUIStack

This stack deploys a modular architecture for ComfyUI with optional Avatar App and Avatar Gallery components.

Deployment Types:
1. ComfyUI: Deploys only the ComfyUI service
2. ComfyUIWithAvatarApp: Deploys ComfyUI and the Avatar App
3. FullStack: Deploys ComfyUI, Avatar App, and Avatar Gallery (default)

Usage:
- Default deployment (FullStack): cdk deploy
- ComfyUI only: cdk deploy --c DeploymentType=ComfyUI
- ComfyUI with Avatar App: cdk deploy --c DeploymentType=ComfyUIWithAvatarApp

Key Components:
- ComfyUI: Always deployed
- Avatar App: Deployed in ComfyUIWithAvatarApp and FullStack modes
- Avatar Gallery: Only deployed in FullStack mode

Shared Resources:
- VPC, ECS Cluster, and other networking components
- Cognito User Pool for authentication
- CloudFront distributions and ALBs for ComfyUI and Avatar components

Notes:
- Ensure all required environment variables are set before deployment
- Review Instace-type g5.4xlarge and adjust it as needed. Change reuqires also update in comfyui-container
- Review and adjust NagSuppressions as needed for your security requirements

Author: Pajtim Matoshi
"""

# these environment variables needs to be set, that the stack is deployable.
certificate_arn = os.environ.get('CERTIFICATE_ARN')
cloudfront_prefix_list_id = os.environ.get('CLOUDFRONT_PREFIX_LIST_ID')
hosted_zone_id = os.environ.get('HOSTED_ZONE_ID')
zone_name = os.environ.get('ZONE_NAME')
record_name_comfyui = os.environ.get('RECORD_NAME_COMFYUI')
record_name_avatar_app = os.environ.get('RECORD_NAME_AVATAR_APP')
record_name_avatar_gallery = os.environ.get('RECORD_NAME_AVATAR_GALLERY')
model_bucket_name = os.environ.get("MODEL_BUCKET_NAME")

class ComfyUIStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        deployment_type = self.node.try_get_context("DeploymentType") or "FullStack"

        if deployment_type not in ["ComfyUI", "ComfyUIWithAvatarApp", "FullStack"]:
            raise ValueError(f"Invalid deployment type: {deployment_type}. "
                             "Must be one of: ComfyUI, ComfyUIWithAvatarApp, FullStack")


        unique_input = f"{self.account}-{self.region}"
        unique_hash = hashlib.sha256(unique_input.encode('utf-8')).hexdigest()[:10]
        suffix = unique_hash.lower()

        # Check for required environment variables
        required_vars = ['CERTIFICATE_ARN', 'CLOUDFRONT_PREFIX_LIST_ID', 'HOSTED_ZONE_ID', 'ZONE_NAME', 'RECORD_NAME_COMFYUI' ]

        if deployment_type in ['ComfyUIWithAvatarApp', 'FullStack']:
            required_vars.append('RECORD_NAME_AVATAR_APP')
            required_vars.append('MODEL_BUCKET_NAME')
            # Reference the existing bucket
            model_bucket = s3.Bucket.from_bucket_name(self, "ModelBucket", model_bucket_name)

        if deployment_type == 'FullStack':
            required_vars.append('RECORD_NAME_AVATAR_GALLERY')

        missing_vars = [var for var in required_vars if not os.environ.get(var)]

        if missing_vars:
            raise ValueError(f"Missing required environment variables for deployment type '{deployment_type}': {', '.join(missing_vars)}")


        vpc = ec2.Vpc(self, "ComfyVPC",
                    max_azs=2,
                    subnet_configuration=[
                        ec2.SubnetConfiguration(
                            name="Public",
                            subnet_type=ec2.SubnetType.PUBLIC,
                            cidr_mask=24
                        ),
                        ec2.SubnetConfiguration(
                            name="Private",
                            subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                            cidr_mask=24
                        )
                    ])

        # Enable VPC Flow Logs
        flow_log = ec2.FlowLog(
            self,
            "FlowLog",
            resource_type=ec2.FlowLogResourceType.from_vpc(vpc),
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(),
        )


        # geo restriction according FATF Blacklist recommendation.
        # Can be changed for your use case
        geo_restriction = cloudfront.GeoRestriction.denylist(
            'KP', 'IR', 'MM'
        )

        # Reference exiting Route53 hosted zone
        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self, 
            "Route53HostedZone",
            hosted_zone_id=hosted_zone_id,
            zone_name=zone_name
        )

        # Retrieve an existing certificate
        certificate = acm.Certificate.from_certificate_arn(
            self,
            "ExistingCertificate", 
            certificate_arn=certificate_arn
        )

        comfyui_alb_security_group = ec2.SecurityGroup(
            self,
            "ComfyUIALBSecurityGroup",
            security_group_name="ComfyUIALBSecurityGroup",
            vpc=vpc,
            description="Security group for ComfyUI ALB"
        )

        # Create Auto Scaling Group Security Group
        asg_security_group = ec2.SecurityGroup(
            self,
            "AsgSecurityGroup",
            security_group_name="ComfyUIAsgSecurityGroup",
            security_group_name="ComfyUIAsgSecurityGroup",
            vpc=vpc,
            description="Security Group for ASG",
            allow_all_outbound=True,
        )

        # Allow inbound traffic on port 80
        asg_security_group.add_ingress_rule(
            peer=comfyui_alb_security_group,
            connection=ec2.Port.tcp(80),
            description="Allow inbound traffic on port 80",
        )
        # Allow inbound traffic on port 443
        asg_security_group.add_ingress_rule(
            peer=comfyui_alb_security_group,
            connection=ec2.Port.tcp(443),
            description="Allow inbound traffic on port 443",
        )

        ec2_role = iam.Role(
            self,
            "EC2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedEC2InstanceDefaultPolicy")
            ]
        )

        efs_security_group = ec2.SecurityGroup(
            self,
            "EFSSecurityGroup",
            security_group_name="EFSSecurityGroup",
            vpc=vpc,
            description="Security Group for EFS",
            allow_all_outbound=True,
        )

        efs_file_system = efs.FileSystem(
            self,
            "ComfyUIEFS",
            vpc=vpc,
            lifecycle_policy=efs.LifecyclePolicy.AFTER_365_DAYS,
            performance_mode=efs.PerformanceMode.GENERAL_PURPOSE,
            throughput_mode=efs.ThroughputMode.ELASTIC,
            removal_policy=RemovalPolicy.DESTROY,
            security_group=efs_security_group
        )

        efs_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(2049),
            description="Allow NFS traffic from within the VPC",
        )

        cluster_name="ComfyUICluster"
        user_data_script = ec2.UserData.for_linux()
        user_data_script.add_commands(f"""
        #!/bin/bash 
        set -e  # Exit immediately if a command exits with a non-zero status.

        # Log all output
        exec > >(tee /var/log/user-data.log) 2>&1

        echo "Starting user data script execution"

        yum install -y amazon-efs-utils awscli

        COMFY_UID=1010
        COMFY_GID=1010

        # Setup NVMe instance store 
        NVME_DEVICE=/dev/nvme1n1 
        NVME_MOUNT=/mnt/nvme 
        mkdir -p $NVME_MOUNT 

        if [ -e $NVME_DEVICE ]; then 
            echo "NVMe device found, formatting and mounting"
            mkfs -t xfs -f $NVME_DEVICE 
            mount $NVME_DEVICE $NVME_MOUNT 
            echo "$NVME_DEVICE $NVME_MOUNT xfs defaults,noatime 0 2" >> /etc/fstab 
        else 
            echo "NVMe instance store not found"
        fi 

        # Mount EFS 
        EFS_ID='{efs_file_system.file_system_id}' 
        EFS_MOUNT='/home/user/opt/ComfyUI' 

        echo "Mounting EFS with ID: $EFS_ID"
        mkdir -p $EFS_MOUNT 
        mount -t efs -o iam,tls $EFS_ID:/ $EFS_MOUNT 
        echo "# EFS mount" >> /etc/fstab 
        echo "$EFS_ID:/ $EFS_MOUNT efs defaults,_netdev 0 0" >> /etc/fstab 

        # Create necessary directories 
        mkdir -p $NVME_MOUNT/comfyui/models

        # Check if the model bucket name is provided
        if [ -n "{model_bucket.bucket_name}" ]; then
            echo "Syncing models from S3 bucket: {model_bucket.bucket_name}"
            aws s3 sync s3://{model_bucket.bucket_name}/models $EFS_MOUNT/models --no-progress
        else
            echo "No model bucket specified, skipping S3 sync."
        fi

        # Set correct permissions 
        echo "Setting permissions for COMFY_UID: $COMFY_UID and COMFY_GID: $COMFY_GID"
        chown -R $COMFY_UID:$COMFY_GID $NVME_MOUNT $EFS_MOUNT
        chmod -R 755 $EFS_MOUNT

        # Verify mounts 
        echo "Mounted filesystems:"
        df -h

        echo "Enabling GPU support for ECS"
        echo 'ECS_ENABLE_GPU_SUPPORT=true' >> /etc/ecs/ecs.config
        echo 'ECS_CLUSTER={cluster_name}' >> /etc/ecs/ecs.config

        echo "Restarting Docker service"
        systemctl restart docker 

        echo "User data script execution completed"
        """
        )

        comfyui_workflow_asg = autoscaling.AutoScalingGroup(
            self,
            "ComfyUIWorkflowASG",
            auto_scaling_group_name="ComfyUIWorkflowASG",
            vpc=vpc,
            instance_type=ec2.InstanceType("g5.4xlarge"), #TODO change to xlarge or 2xlarge
            machine_image=ecs.EcsOptimizedImage.amazon_linux2(
                hardware_type=ecs.AmiHardwareType.GPU
            ),
            role=ec2_role,
            min_capacity=0,
            max_capacity=1,
            desired_capacity=1,
            new_instances_protected_from_scale_in=False,
            security_group=asg_security_group,
            user_data=user_data_script,
            block_devices=[
                autoscaling.BlockDevice(
                    device_name="/dev/xvda",
                    volume=autoscaling.BlockDeviceVolume.ebs(volume_size=100, 
                                                             encrypted=True,
                                                             volume_type=autoscaling.EbsDeviceVolumeType.GP3)
                )
            ],
            vpc_subnets=ec2.SubnetSelection(
                subnets=[
                    ec2.Subnet.from_subnet_attributes(self, "WorkflowSubnet", 
                                                    subnet_id=vpc.private_subnets[1].subnet_id, 
                                                    availability_zone="us-east-1b"
                                                    )
                ]
            )
        )

        comfyui_workflow_asg.apply_removal_policy(RemovalPolicy.DESTROY)


        asg_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(2049),
            description="Allow NFS traffic from within the VPC",
        )

        efs_security_group.add_ingress_rule(
            peer=asg_security_group,
            connection=ec2.Port.tcp(2049),
            description="Allow NFS traffic from within the VPC",
        )

        cpu_utilization_metric = cloudwatch.Metric(
            namespace='AWS/EC2',
            metric_name='CPUUtilization',
            dimensions_map={
                'AutoScalingGroupName': comfyui_workflow_asg.auto_scaling_group_name
            },
            statistic='Average',
            period=Duration.minutes(1)
        )

        scaling_policy = autoscaling.CfnScalingPolicy(
            self,
            "SimpleScalingPolicy",
            auto_scaling_group_name=comfyui_workflow_asg.auto_scaling_group_name,
            policy_type="SimpleScaling",
            adjustment_type="ExactCapacity",
            scaling_adjustment=0,
            cooldown=str(Duration.seconds(60).to_seconds()),
        )

        cpu_alarm = cloudwatch.CfnAlarm(
            self,
            "CPUAlarm",
            comparison_operator="LessThanThreshold",
            evaluation_periods=120,
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            period=60,
            statistic="Average",
            threshold=1,
            alarm_description="Alarm when server avg CPU usage less than 1%",
            dimensions=[
                {
                    "name": "AutoScalingGroupName",
                    "value": comfyui_workflow_asg.auto_scaling_group_name
                }
            ],
            alarm_actions=[scaling_policy.ref]
        )

        # Create an ECS Cluster
        cluster = ecs.Cluster(
            self, "ComfyUICluster", 
            vpc=vpc, 
            cluster_name=cluster_name, 
            container_insights=True
        )
        
        # Create ASG Capacity Provider for the ECS Cluster
        capacity_provider = ecs.AsgCapacityProvider(
            self, "AsgCapacityProvider",
            auto_scaling_group=comfyui_workflow_asg,
            enable_managed_scaling=False,
            enable_managed_termination_protection=False,
            target_capacity_percent=100
        )

        cluster.add_asg_capacity_provider(capacity_provider)

        # Create IAM Role for ECS Task Execution
        task_exec_role = iam.Role(
            self,
            "ECSTaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        task_exec_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonElasticFileSystemClientFullAccess")
        )

        # ECR Repository
        ecr_repository_comfyui = ecr.Repository.from_repository_name(
            self, 
            "comfyui", 
            repository_name=f"comfyui")

        # CloudWatch Logs Group
        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name="/ecs/comfy-ui",
            removal_policy=RemovalPolicy.DESTROY,
        )

        efs_volume = ecs.Volume(
            name="efs-volume",
            efs_volume_configuration=ecs.EfsVolumeConfiguration(
                file_system_id=efs_file_system.file_system_id,
                transit_encryption="ENABLED",
                authorization_config=ecs.AuthorizationConfig(
                    iam="ENABLED"
                )
            ),
        )

        nvme_volume = ecs.Volume(
            name="nvme-volume",
            host=ecs.Host(source_path="/mnt/nvme/comfyui")
        )

        # COMFYUI CONFIGURATION
        comfyui_task_definition = ecs.Ec2TaskDefinition(
            self,
            "ComfyUIWorkflowTaskDefinition",
            network_mode=ecs.NetworkMode.AWS_VPC,
            task_role=task_exec_role,
            execution_role=task_exec_role,
            volumes=[
                efs_volume,
                nvme_volume
            ]
        )

        # Add container to the task definition
        comfyui_workflow_container = comfyui_task_definition.add_container(
            "ComfyUIWorkflowContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repository_comfyui, "latest"),
            gpu_count=1,
            memory_limit_mib=63500,
            cpu=15500,
            logging=ecs.LogDriver.aws_logs(stream_prefix="comfy-ui", log_group=log_group),
            environment={
                "MODEL_PATH": "/mnt/nvme/comfyui/models",  # TODO: check nvme path mount in comfyui yaml
                "EFS_MOUNT_PATH": "/home/user/opt/ComfyUI",
            },
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8181/system_stats || exit 1"],
                interval=Duration.seconds(15),
                timeout=Duration.seconds(10),
                retries=8,
                start_period=Duration.seconds(180)
            ),
            user="1010"
        )

        # Mount the host volume to the container
        comfyui_workflow_container.add_mount_points(
            ecs.MountPoint(
                container_path="/home/user/opt/ComfyUI",
                source_volume="efs-volume",
                read_only=False
            ),
            ecs.MountPoint(
                container_path="/mnt/nvme/comfyui",
                source_volume="nvme-volume",
                read_only=False
            )
        )

        # Port mappings for the container
        comfyui_workflow_container.add_port_mappings(
            ecs.PortMapping(
                container_port=8181,
                app_protocol=ecs.AppProtocol.http,
                name="comfyui-port-mapping",
                protocol=ecs.Protocol.TCP,
            )
        )

        # Create ECS Service Security Group
        ecs_service_security_group = ec2.SecurityGroup(
            self,
            "ServiceSecurityGroup",
            security_group_name="ComfyUIServiceSecurityGroup",
            vpc=vpc,
            description="Security Group for ComfyUI ECS Service",
            allow_all_outbound=True,
        )

        efs_security_group.add_ingress_rule(
            peer=ecs_service_security_group,
            connection=ec2.Port.tcp(2049),
            description="Allow NFS traffic from within the VPC",
        )


        # Create ECS Service for ComfyUI Workflow Instance. Which is used as GUI, not API Backend.
        comfyui_workflow_service = ecs.Ec2Service(
            self,
            "ComfyUIWorkflowService",
            service_name="ComfyUIWorkflowService",
            cluster=cluster,
            task_definition=comfyui_task_definition,
            capacity_provider_strategies=[
                ecs.CapacityProviderStrategy(
                    capacity_provider=capacity_provider.capacity_provider_name, 
                    weight=1
                )
            ],
            security_groups=[ecs_service_security_group],
            health_check_grace_period=Duration.seconds(480),
            desired_count=1,
            min_healthy_percent=0, #allowing to scale down to zero tasks
            max_healthy_percent=100
        )

        comfyui_alb_security_group.add_ingress_rule(
            peer=ec2.Peer.prefix_list(cloudfront_prefix_list_id),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP traffic from CloudFront",
        )

        comfyui_alb_security_group.add_ingress_rule(
            peer=ec2.Peer.prefix_list(cloudfront_prefix_list_id),
            connection=ec2.Port.tcp(443),
            description="Allow HTTP traffic from CloudFront",
        )

        # External ALB for ComfyUI
        comfyui_alb = elbv2.ApplicationLoadBalancer(
            self, 
            "ComfyUIALB", 
            vpc=vpc, 
            load_balancer_name="ComfyUIALB", 
            internet_facing=True,
            security_group=comfyui_alb_security_group)

        # log bucket for complete app stack
        avatar_log_bucket = s3.Bucket(
            self, 
            "AvatarAppLogBucket", 
            bucket_name= f"comfyui-avatar-log-bucket-{suffix}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER
        )

        comfyui_alb.log_access_logs(
            avatar_log_bucket, 
            prefix="load-balancer-logs")

        trail = cloudtrail.Trail(
            self, 
            "ComfyUICloudTrail",
            bucket=avatar_log_bucket,
            s3_key_prefix="cloudtrail",
            cloud_watch_logs_retention=logs.RetentionDays.ONE_MONTH,
            trail_name=f"ComfyUICloudTrail",
            send_to_cloud_watch_logs=True,
            management_events=cloudtrail.ReadWriteType.ALL,
            include_global_service_events=True
        )

        # ComfyUI CloudFront distribution
        comfyui_cloudfront_distribution = cloudfront.Distribution(
            self, 
            "ComfyUIDistribution",                                  
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.LoadBalancerV2Origin(
                    comfyui_alb,
                    protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                    origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2]
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED, 
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER, 
            ),
            domain_names=[record_name_comfyui],
            certificate=certificate,
            enable_ipv6=False,
            log_bucket=avatar_log_bucket,
            log_file_prefix="comfyui-cloudfront-logs/",
            log_includes_cookies=True,
            geo_restriction=geo_restriction
        )

        comfyui_url = record_name_comfyui
        # Add Route 53 A Alias records for ComfyUI and Avatars App
        comfyui_record = route53.ARecord(
            self, "ComfyUIRecord",
            zone=hosted_zone,
            record_name=comfyui_url,
            target=route53.RecordTarget.from_alias(route53_targets.CloudFrontTarget(comfyui_cloudfront_distribution))
        )
        
        lambda_role = iam.Role(
            self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AutoScalingFullAccess"),
            ]
        )

        lambda_role.add_to_policy(iam.PolicyStatement(
            actions=["ecs:DescribeServices", 
                     "ecs:ListTasks",
                     "elasticloadbalancing:ModifyListener",
                     "elasticloadbalancing:ModifyRule",
                     "elasticloadbalancing:DescribeRules",
                     "elasticloadbalancing:DescribeListeners",
                     "ecs:DescribeServices",
                     "ecs:UpdateService",
                     "ssm:SendCommand"],
            resources=["*"]
        ))

        admin_lambda = lambda_.Function(
            self,
            "AdminFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            role=lambda_role,
            handler="admin.handler",
            code=lambda_.Code.from_asset("./comfyui_aws_stack/admin_lambda"),
            timeout=Duration.seconds(amount=60),
            memory_size=512
        )

        scalein_listener_lambda = lambda_.Function(
            self,
            "ScaleinListenerFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            role=lambda_role,
            handler="scalein_listener.handler",
            code=lambda_.Code.from_asset("./comfyui_aws_stack/admin_lambda"),
            timeout=Duration.seconds(amount=60),
            memory_size=512
        )

        # Add target groups for ECS service
        ecs_comfyui_workflow_target_group = elbv2.ApplicationTargetGroup(
            self,
            "EcsComfyUIWorkflowTargetGroup",
            target_group_name="EcsComfyUIWorkflowTargetGroup",
            port=8181,
            vpc=vpc,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            targets=[
                comfyui_workflow_service.load_balancer_target(
                    container_name=comfyui_workflow_container.container_name ,container_port=8181
                )],
            health_check=elbv2.HealthCheck(
                enabled=True,
                path="/system_stats",
                port="8181",
                protocol=elbv2.Protocol.HTTP,
                healthy_http_codes="200",  # Adjust as needed
                interval=Duration.seconds(60),
                timeout=Duration.seconds(30),
                unhealthy_threshold_count=8,
                healthy_threshold_count=2,
            )
        )

        # ecs_comfyui_workflow_target_group.add_target(comfyui_workflow_service)

        lambda_admin_target_group = elbv2.ApplicationTargetGroup(
            self,
            "LambdaAdminTargetGroup",
            target_group_name="LambdaAdminTargetGroup",
            vpc=vpc,
            target_type=elbv2.TargetType.LAMBDA,
            targets=[targets.LambdaTarget(admin_lambda)]
        )

        ##########################################################
        # COGNITO - USER POOL SETUP
        ##########################################################
        cognito_custom_domain = f"comfyui-alb-auth-{suffix}"
        comfyui_alb_dns = comfyui_alb.load_balancer_dns_name

        # Create the user pool that holds our users
        user_pool = cognito.UserPool(
            self,
            "ComfyUIuserPool",
            account_recovery=cognito.AccountRecovery.EMAIL_AND_PHONE_WITHOUT_MFA,
            auto_verify=cognito.AutoVerifiedAttrs(email=True, phone=True),
            self_sign_up_enabled=False,
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(mutable=True, required=False),
                given_name=cognito.StandardAttribute(mutable=True, required=False),
                family_name=cognito.StandardAttribute(mutable=True, required=False)
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            advanced_security_mode=cognito.AdvancedSecurityMode.ENFORCED
        )

        # Add a custom domain for the hosted UI
        user_pool_custom_domain = user_pool.add_domain(
            "user-pool-domain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=cognito_custom_domain
            )
        )
        
        # Create an app client that the ALB can use for authentication
        user_pool_client = user_pool.add_client(
            "alb-app-client",
            user_pool_client_name="AlbAuthentication",
            generate_secret=True,
            o_auth=cognito.OAuthSettings(
                callback_urls=[
                    f"https://{comfyui_alb_dns}/oauth2/idpresponse",
                    f"https://{comfyui_alb_dns}",
                    f"https://{comfyui_url}",
                    f"https://{comfyui_url}/oauth2/idpresponse",
                    f"https://{comfyui_cloudfront_distribution.domain_name}",
                    f"https://{comfyui_cloudfront_distribution.domain_name}/oauth2/idpresponse"
                ],
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID
                ]
            ),
            supported_identity_providers=[
                cognito.UserPoolClientIdentityProvider.COGNITO
            ]
        )

        # Logout URLs and redirect URIs can't be set in CDK constructs natively ...yet
        user_pool_client_cf: cognito.CfnUserPoolClient = user_pool_client.node.default_child
        user_pool_client_cf.logout_ur_ls = [
            f"https://{comfyui_url}"
        ]

        user_pool_full_domain = user_pool_custom_domain.base_url()
        redirect_uri = urllib.parse.quote('https://' + comfyui_alb_dns)
        user_pool_logout_url = f"{user_pool_full_domain}/logout?" \
                                    + f"client_id={user_pool_client.user_pool_client_id}&" \
                                    + f"logout_uri={redirect_uri}"

        user_pool_user_info_url = f"{user_pool_full_domain}/oauth2/userInfo"

        cognito_secrets = secretsmanager.Secret(
            self,
            "CognitoSecrets",
            secret_name="CognitoSecrets",
            description="Cognito User Pool, Client ID and Secret",
            secret_object_value={
                "COGNITO_POOL_ID": SecretValue.unsafe_plain_text(user_pool.user_pool_id),
                "COGNITO_APP_CLIENT_ID": SecretValue.unsafe_plain_text(user_pool_client.user_pool_client_id),
                "COGNITO_APP_CLIENT_SECRET": user_pool_client.user_pool_client_secret,
            },
        )

        # ComfyUI Listener and Authenticate over Cognito Rule
        comfyui_listener = comfyui_alb.add_listener(
            "ComfyUIHttpListener", 
            port=443,
            open=False,
            certificates=[certificate],
            protocol=elbv2.ApplicationProtocol.HTTPS,
            default_action=elb_actions.AuthenticateCognitoAction(
                next=elbv2.ListenerAction.forward([ecs_comfyui_workflow_target_group]),
                user_pool=user_pool,
                user_pool_client=user_pool_client,
                user_pool_domain=user_pool_custom_domain,
            )
        )

        ##########################################################
        # ComfyUI Admin Utils
        ##########################################################
        lambda_admin_rule = elbv2.ApplicationListenerRule(
            self,
            "LambdaAdminRule",
            listener=comfyui_listener,
            priority=5,
            conditions=[elbv2.ListenerCondition.path_patterns(["/admin"])],
            action=elb_actions.AuthenticateCognitoAction(
                next=elbv2.ListenerAction.forward([lambda_admin_target_group]),
                user_pool=user_pool,
                user_pool_client=user_pool_client,
                user_pool_domain=user_pool_custom_domain,
            ),
        )

        admin_lambda.add_environment("ECS_CLUSTER_NAME", cluster.cluster_name)
        admin_lambda.add_environment("WORKFLOW_ASG_NAME", comfyui_workflow_service.service_name)
        admin_lambda.add_environment("WORKFLOW_SERVICE_NAME", comfyui_workflow_asg.auto_scaling_group_name)
        admin_lambda.add_environment("LISTENER_ARN", comfyui_listener.listener_arn)

        comfyui_workflow_asg.add_lifecycle_hook(
            "ComfyUITerminationHook",
            lifecycle_transition=autoscaling.LifecycleTransition.INSTANCE_TERMINATING,
            heartbeat_timeout=Duration.seconds(30),
            default_result=autoscaling.DefaultResult.CONTINUE,
            notification_target=hooktargets.FunctionHook(admin_lambda)
        )

        #ScaleIn Listener and topic subscription
        scalein_listener_lambda.add_environment("ASG_NAME", comfyui_workflow_asg.auto_scaling_group_name)
        scalein_listener_lambda.add_environment("LISTENER_RULE_ARN", lambda_admin_rule.listener_rule_arn)
        
        # Add authentication action as the first priority rule
        auth_rule = comfyui_listener.add_action(
            "AuthenticateRule",
            priority=25, 
            action=elb_actions.AuthenticateCognitoAction(
                next=elbv2.ListenerAction.forward([ecs_comfyui_workflow_target_group]),
                user_pool=user_pool,
                user_pool_client=user_pool_client,
                user_pool_domain=user_pool_custom_domain,
            ),
            conditions=[elbv2.ListenerCondition.path_patterns(["/*"])]
        )

        trail.add_lambda_event_selector([
            admin_lambda,
            scalein_listener_lambda
        ])    

        #############################################################
        # COMFYUI-AVATAR APP and Gallery depending on DeploymentType
        #############################################################

        if deployment_type in ["ComfyUIWithAvatarApp", "FullStack"]:

            comfyui_api_asg = autoscaling.AutoScalingGroup(
                self,
                "ComfyUIApiASG",
                auto_scaling_group_name="ComfyUIApiASG",
                vpc=vpc,
                instance_type=ec2.InstanceType("g5.xlarge"),
                machine_image=ecs.EcsOptimizedImage.amazon_linux2(
                    hardware_type=ecs.AmiHardwareType.GPU
                ),
                role=ec2_role,
                min_capacity=0,
                max_capacity=4,
                desired_capacity=1,
                new_instances_protected_from_scale_in=False,
                security_group=asg_security_group,
                user_data=user_data_script,
                block_devices=[
                    autoscaling.BlockDevice(
                        device_name="/dev/xvda",
                        volume=autoscaling.BlockDeviceVolume.ebs(volume_size=100, 
                                                                encrypted=True,
                                                                volume_type=autoscaling.EbsDeviceVolumeType.GP3)
                    )
                ],
                vpc_subnets=ec2.SubnetSelection(
                    subnets=[
                        ec2.Subnet.from_subnet_attributes(self, "APISubnet", 
                                                        subnet_id=vpc.private_subnets[1].subnet_id, 
                                                        availability_zone="us-east-1b"
                                                        )
                    ]
                )
            )

            # COMFYUI CONFIGURATION
            comfyui_api_task_definition = ecs.Ec2TaskDefinition(
                self,
                "ComfyUIAPITaskDefinition",
                network_mode=ecs.NetworkMode.AWS_VPC,
                task_role=task_exec_role,
                execution_role=task_exec_role,
                volumes=[
                    efs_volume,
                    nvme_volume
                ]
            )

            # Add container to the task definition
            comfyui_api_container = comfyui_api_task_definition.add_container(
                "ComfyUIAPIContainer",
                image=ecs.ContainerImage.from_ecr_repository(ecr_repository_comfyui, "latest"),
                gpu_count=1,
                memory_limit_mib=15700,
                cpu=4000,
                logging=ecs.LogDriver.aws_logs(stream_prefix="comfy-ui", log_group=log_group),
                environment={
                    "MODEL_PATH": "/mnt/nvme/comfyui/models",  # TODO: check nvme path mount in comfyui yaml
                    "EFS_MOUNT_PATH": "/home/user/opt/ComfyUI",
                },
                health_check=ecs.HealthCheck(
                    command=["CMD-SHELL", "curl -f http://localhost:8181/system_stats || exit 1"],
                    interval=Duration.seconds(15),
                    timeout=Duration.seconds(10),
                    retries=8,
                    start_period=Duration.seconds(180)
                ),
                user="1010"
            )

            # Mount the host volume to the container
            comfyui_api_container.add_mount_points(
                ecs.MountPoint(
                    container_path="/home/user/opt/ComfyUI",
                    source_volume="efs-volume",
                    read_only=False
                ),
                ecs.MountPoint(
                    container_path="/mnt/nvme/comfyui",
                    source_volume="nvme-volume",
                    read_only=False
                )
            )

            # Port mappings for the container
            comfyui_api_container.add_port_mappings(
                ecs.PortMapping(
                    container_port=8181,
                    app_protocol=ecs.AppProtocol.http,
                    name="comfyui-api-port-mapping",
                    protocol=ecs.Protocol.TCP,
                )
            )

            api_capacity_provider = ecs.AsgCapacityProvider(
                self, "ApiAsgCapacityProvider",
                auto_scaling_group=comfyui_api_asg,
                enable_managed_scaling=False,
                enable_managed_termination_protection=False,
                target_capacity_percent=100
            )

            cluster.add_asg_capacity_provider(api_capacity_provider)

            comfyui_api_service = ecs.Ec2Service(
                self,
                "ComfyUIApiService",
                service_name="ComfyUIApiService",
                cluster=cluster,
                task_definition=comfyui_api_task_definition,
                capacity_provider_strategies=[
                    ecs.CapacityProviderStrategy(
                        capacity_provider=api_capacity_provider.capacity_provider_name,
                        weight=1
                    )
                ],
                security_groups=[ecs_service_security_group],
                health_check_grace_period=Duration.seconds(480),
                desired_count=1,
                min_healthy_percent=0, #allowing to scale down to zero tasks
                max_healthy_percent=100
            )

            # add admin environment variables
            admin_lambda.add_environment("API_ASG_NAME", comfyui_api_asg.auto_scaling_group_name)
            admin_lambda.add_environment("API_SERVICE_NAME", comfyui_api_service.service_name)

            # Combined Security Group for Avatar App and optional Gallery
            avatar_services_security_group = ec2.SecurityGroup(
                self, "AvatarServicesSecurityGroup",
                security_group_name="AvatarServicesSecurityGroup",
                vpc=vpc,
                description="Security Group for Avatar ECS Services",
                allow_all_outbound=True,
            )

            ecs_service_security_group.add_ingress_rule(
                peer=avatar_services_security_group,
                connection=ec2.Port.tcp(8181),
                description="Allow traffic from Avatar Containers on port 8181",
            )

            # Allow Service Connect ports
            ecs_service_security_group.add_ingress_rule(
                peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
                connection=ec2.Port.tcp(8181),
                description="Allow Service Connect traffic",
            )

            # Allow EFS access from the ECS tasks
            ecs_service_security_group.add_ingress_rule(
                peer=efs_security_group,
                connection=ec2.Port.tcp(2049),
                description="Allow EFS access",
            )

            # Security Group for internal ALB
            comfyui_alb_internal_security_group = ec2.SecurityGroup(
                self,
                "ComfyUIALBInternalSecurityGroup",
                security_group_name="ComfyUIALBInternalSecurityGroup",
                vpc=vpc,
                description="Security group for internal ComfyUI ALB"
            )

            comfyui_alb_internal_security_group.add_ingress_rule(
                peer=avatar_services_security_group,
                connection=ec2.Port.tcp(8181),
                description="Allow TCP Traffic from Avatar App",
            )

            ecs_service_security_group.add_ingress_rule(
                peer=comfyui_alb_internal_security_group,
                connection=ec2.Port.tcp(8181),
                description="Allow traffic from internal ComfyUI ALB on port 8181",
            )

            # Internal ALB for ComfyUI
            comfyui_alb_internal = elbv2.ApplicationLoadBalancer(
                self, 
                "ComfyUIALBInternal", 
                vpc=vpc, 
                load_balancer_name="ComfyUIALBInternal", 
                internet_facing=False,
                security_group=comfyui_alb_internal_security_group)

            comfyui_alb_internal.log_access_logs(
                avatar_log_bucket, 
                prefix="comfyui-alb-internal-load-balancer-logs")

            avatar_alb_security_group = ec2.SecurityGroup(
                self,
                "AvatarALBSecurityGroup",
                security_group_name="AvatarALBSecurityGroup",
                security_group_name="AvatarALBSecurityGroup",
                vpc=vpc,
                description="Security group for Avatar ALB"
            )

            avatar_alb_security_group.add_ingress_rule(
                peer=ec2.Peer.prefix_list(cloudfront_prefix_list_id),
                connection=ec2.Port.tcp(443),
                description="Allow HTTPS traffic from CloudFront",
            )

            ecs_service_security_group.add_ingress_rule(
                peer=avatar_alb_security_group,
                connection=ec2.Port.tcp(8181),
                description="Allow traffic from Avatar Containers on port 8181",
            )

            # Add target group for ECS service for the internal ALB
            ecs_comfyui_api_target_group = elbv2.ApplicationTargetGroup(
                self,
                "EcsComfyUIAPITargetGroupInternal",
                target_group_name="EcsComfyUIAPITargetGroupInternal",
                port=8181,
                vpc=vpc,
                protocol=elbv2.ApplicationProtocol.HTTP,
                target_type=elbv2.TargetType.IP,
                targets=[
                    comfyui_api_service.load_balancer_target(
                        container_name=comfyui_api_container.container_name, container_port=8181
                    )],
                health_check=elbv2.HealthCheck(
                    enabled=True,
                    path="/system_stats",
                    port="8181",
                    protocol=elbv2.Protocol.HTTP,
                    healthy_http_codes="200",
                    interval=Duration.seconds(60),
                    timeout=Duration.seconds(30),
                    unhealthy_threshold_count=8,
                    healthy_threshold_count=2,
                ),
                stickiness_cookie_name="COMFY-SESSION",
                stickiness_cookie_duration=Duration.days(1)
            )

            # ecs_comfyui_api_target_group.add_target(comfyui_api_service)

            websocket_listener = comfyui_alb_internal.add_listener(
                "WebSocketListener",
                port=8181,
                open=False,
                protocol=elbv2.ApplicationProtocol.HTTP,
                default_action=elbv2.ListenerAction.forward([ecs_comfyui_api_target_group])
            )

            # Application Load Balancer
            avatar_alb = elbv2.ApplicationLoadBalancer(
                self, 
                "AvatarALB", 
                vpc=vpc, 
                load_balancer_name="AvatarALB", 
                internet_facing=True,
                security_group=avatar_alb_security_group)

            avatar_alb.log_access_logs(
                avatar_log_bucket, 
                prefix="avatar-load-balancer-logs")


            domain_names = [record_name_avatar_app]

            if deployment_type in ["FullStack"]:
                domain_names = [record_name_avatar_app, record_name_avatar_gallery]

            # ComfyUI CloudFront distribution
            avatar_cloudfront_distribution = cloudfront.Distribution(self, "AvatarDistribution",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=origins.LoadBalancerV2Origin(
                        avatar_alb,
                        protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
                        origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2]
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED, 
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER, 
                ),
                domain_names=domain_names,
                certificate=certificate,
                enable_ipv6=False,
                log_bucket=avatar_log_bucket,
                log_file_prefix="avatar-cloudfront-logs/",
                log_includes_cookies=True,
                geo_restriction=geo_restriction
            )


            avatar_cloudfront_distribution.add_behavior(
                path_pattern="/*",
                origin=origins.LoadBalancerV2Origin(avatar_alb),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED, 
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER
            )


            alb_log_role = iam.Role(self, "ALBLogRole",
                assumed_by=iam.ServicePrincipal("elasticloadbalancing.amazonaws.com"),
                description="Role for ALBs to access S3 logging bucket"
            )

            alb_log_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                    "s3:GetBucketAcl",
                ],
                resources=[
                    avatar_log_bucket.bucket_arn,
                    f"{avatar_log_bucket.bucket_arn}/*"
                ]
            ))

            avatar_log_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    actions=[
                        "s3:PutObject",
                        "s3:PutObjectAcl"
                    ],
                    resources=[f"{avatar_log_bucket.bucket_arn}/*"],
                    principals=[
                        iam.ServicePrincipal("cloudfront.amazonaws.com")
                    ],
                    conditions={
                        "StringEquals": {
                            "aws:SourceArn": f"arn:aws:cloudfront::{self.account}:distribution/*"
                        }
                    }
                )
            )

            # Add Route 53 A Alias records for ComfyUI and Avatars App
            avatar_app_record = route53.ARecord(
                self, "AvatarAppRecord",
                zone=hosted_zone,
                record_name=record_name_avatar_app,
                target=route53.RecordTarget.from_alias(route53_targets.CloudFrontTarget(avatar_cloudfront_distribution)),
            )

            avatar_bucket = s3.Bucket(
                self, 
                "ComfyUIAvatarBucket",
                bucket_name=f"comfyui-avatar-{suffix}",
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
                enforce_ssl=True,
                server_access_logs_bucket=avatar_log_bucket,
                server_access_logs_prefix="avatar-bucket-log/"
            )

            trail.add_s3_event_selector([cloudtrail.S3EventSelector(
                bucket=avatar_bucket
            )])

            # ECR Repository
            ecr_repository_avatar_app = ecr.Repository.from_repository_name(
                self, 
                "comfyui-avatar-app", 
                repository_name=f"comfyui-avatar-app")

            # Create IAM Role for ECS Task Execution
            avatar_task_exec_role = iam.Role(
                self,
                "AvatarTaskExecutionRole",
                assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AmazonECSTaskExecutionRolePolicy"
                    )
                ],
            )

            avatar_task_exec_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                ],
                resources=[
                    avatar_bucket.bucket_arn,
                    f"{avatar_bucket.bucket_arn}/*"
                ]
            ))

            # Rekognition moderation
            avatar_task_exec_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "rekognition:DetectModerationLabels",
                    "rekognition:DetectFaces"
                ],
                resources=[f"*"]
            ))
            
            avatar_task_exec_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{self.region}::foundation-model/*"] 
            ))


            ec2_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecs:CreateCluster",
                    "ecs:DeregisterContainerInstance",
                    "ecs:DiscoverPollEndpoint",
                    "ecs:Poll",
                    "ecs:RegisterContainerInstance",
                    "ecs:StartTelemetrySession",
                    "ecs:UpdateContainerInstancesState",
                    "ecs:Submit*",
                    "ec2:DescribeInstances",
                    "ec2:DescribeTags",
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage"                    
                ],
                resources=["*"]
            ))

            ec2_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[f"{log_group.log_group_arn}:*"]
            ))

            ec2_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "autoscaling:CompleteLifecycleAction",
                    "autoscaling:RecordLifecycleActionHeartbeat",
                    "autoscaling:DescribeAutoScalingInstances",
                    "autoscaling:DescribeLifecycleHooks"
                ],
                resources=[f"arn:aws:autoscaling:{self.region}:{self.account}:autoScalingGroup:*"]
            ))

            ec2_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:AttachVolume",
                    "ec2:CreateVolume",
                    "ec2:CreateSnapshot",
                    "ec2:CreateTags",
                    "ec2:DeleteVolume",
                    "ec2:DeleteSnapshot",
                    "ec2:DescribeAvailabilityZones",
                    "ec2:DescribeInstances",
                    "ec2:DescribeVolumes",
                    "ec2:DescribeVolumeAttribute",
                    "ec2:DescribeVolumeStatus",
                    "ec2:DescribeSnapshots",
                    "ec2:CopySnapshot",
                    "ec2:DescribeSnapshotAttribute",
                    "ec2:DetachVolume",
                    "ec2:ModifySnapshotAttribute",
                    "ec2:ModifyVolumeAttribute",
                    "ec2:DescribeTags",
                    "ec2:EnableVolumeIO"
                ],
                resources=["*"]
            ))

            # add policy also to ec2 role, that you can acccess the bucket over the ec2 instance
            ec2_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                ],
                resources=[
                    avatar_bucket.bucket_arn,
                    f"{avatar_bucket.bucket_arn}/*",
                    model_bucket.bucket_arn,
                    f"{model_bucket.bucket_arn}/*",
                ]
            ))

            ec2_role.add_managed_policy(
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonElasticFileSystemClientFullAccess")
            )


            ##########################################################
            # Avatar App Task + Service
            ##########################################################
            avatar_app_task_definition = ecs.FargateTaskDefinition(
                self,
                "AvatarAppTaskDefinition",
                cpu=2048,
                memory_limit_mib=8192,
                task_role=avatar_task_exec_role,
                execution_role=avatar_task_exec_role,
            )

            avatar_app_container = avatar_app_task_definition.add_container(
                "AvatarAppContainer",
                container_name="AvatarAppContainer",
                image=ecs.ContainerImage.from_ecr_repository(ecr_repository_avatar_app, "latest"),
                logging=ecs.LogDriver.aws_logs(stream_prefix="avatar-app", log_group=log_group),
                health_check=ecs.HealthCheck(
                    command=["CMD-SHELL", "curl -f http://localhost:8501/healthz || exit 1"],
                    interval=Duration.seconds(25),
                    timeout=Duration.seconds(20),
                    retries=8,
                    start_period=Duration.seconds(30)
                ),
                environment={
                    "COMFYUI": comfyui_alb_internal.load_balancer_dns_name,
                    "S3_BUCKET": avatar_bucket.bucket_name,
                    "S3_BUCKET_PREFIX": "avatars/"
                },
                secrets={
                    "COGNITO_POOL_ID": ecs.Secret.from_secrets_manager(cognito_secrets, "COGNITO_POOL_ID"),
                    "COGNITO_APP_CLIENT_ID": ecs.Secret.from_secrets_manager(cognito_secrets, "COGNITO_APP_CLIENT_ID"),
                    "COGNITO_APP_CLIENT_SECRET": ecs.Secret.from_secrets_manager(cognito_secrets, "COGNITO_APP_CLIENT_SECRET")
                }
            )

            avatar_app_container.add_port_mappings(
                ecs.PortMapping(container_port=8501)
            )

            avatar_services_security_group.add_ingress_rule(
                peer=avatar_alb_security_group,
                connection=ec2.Port.tcp(8501),
                description="Allow traffic from Avatar ALB on port 8501",
            )

            avatar_app_service = ecs.FargateService(
                self,
                "AvatarAppFargateService",
                service_name="AvatarAppService",
                service_name="AvatarAppService",
                cluster=cluster,
                task_definition=avatar_app_task_definition,
                desired_count=1,
                security_groups=[avatar_services_security_group]
            )

            avatar_app_target_group = elbv2.ApplicationTargetGroup(
                self,
                "AvatarAppTargetGroup",
                port=8501,
                vpc=vpc,
                protocol=elbv2.ApplicationProtocol.HTTP,
                target_type=elbv2.TargetType.IP,
                health_check=elbv2.HealthCheck(
                    enabled=True,
                    path="/healthz",
                    port="8501",
                    protocol=elbv2.Protocol.HTTP,
                    healthy_http_codes="200",
                    interval=Duration.seconds(30),
                    timeout=Duration.seconds(5),
                    unhealthy_threshold_count=3,
                    healthy_threshold_count=2,
                )
            )

            avatar_app_target_group.add_target(avatar_app_service)

            avatar_listener = avatar_alb.add_listener(
                "AvatarAppListener", 
                port=443,
                open=False,
                protocol=elbv2.ApplicationProtocol.HTTPS,
                certificates=[certificate],
                default_action=elbv2.ListenerAction.forward([avatar_app_target_group])
            )

            avatar_app_rule = elbv2.ApplicationListenerRule(
                self,
                "AvatarAppRule",
                listener=avatar_listener,
                priority=1,
                conditions=[elbv2.ListenerCondition.host_headers([record_name_avatar_app])],
                action=elbv2.ListenerAction.forward([avatar_app_target_group])
            )

            ##########################################################
            # Avatar Gallery Task + Service
            ##########################################################

            if deployment_type in ["FullStack"]:

                avatar_gallery_record = route53.ARecord(
                    self, "AvatarGalleryRecord",
                    zone=hosted_zone,
                    record_name=record_name_avatar_gallery,
                    target=route53.RecordTarget.from_alias(route53_targets.CloudFrontTarget(avatar_cloudfront_distribution)),
                )

                # ECR Repository
                ecr_repository_avatar_gallery = ecr.Repository.from_repository_name(
                    self, 
                    "comfyui-avatar-gallery", 
                    repository_name=f"comfyui-avatar-gallery")
                
                avatar_gallery_task_definition = ecs.FargateTaskDefinition(
                    self,
                    "AvatarGalleryTaskDefinition",
                    cpu=2048,
                    memory_limit_mib=4096,
                    task_role=avatar_task_exec_role,
                    execution_role=avatar_task_exec_role,
                )

                avatar_gallery_container = avatar_gallery_task_definition.add_container(
                    "AvatarGalleryContainer",
                    container_name="AvatarGalleryContainer",
                    image=ecs.ContainerImage.from_ecr_repository(ecr_repository_avatar_gallery, "latest"),
                    logging=ecs.LogDriver.aws_logs(stream_prefix="avatar-gallery", log_group=log_group),
                    health_check=ecs.HealthCheck(
                        command=["CMD-SHELL", "curl -f http://localhost:8502/healthz || exit 1"],
                        interval=Duration.seconds(15),
                        timeout=Duration.seconds(10),
                        retries=8,
                        start_period=Duration.seconds(30)
                    ),
                    environment={
                        "S3_BUCKET": avatar_bucket.bucket_name,
                        "S3_BUCKET_PREFIX": "avatars/"
                    },
                    secrets={
                        "COGNITO_POOL_ID": ecs.Secret.from_secrets_manager(cognito_secrets, "COGNITO_POOL_ID"),
                        "COGNITO_APP_CLIENT_ID": ecs.Secret.from_secrets_manager(cognito_secrets, "COGNITO_APP_CLIENT_ID"),
                        "COGNITO_APP_CLIENT_SECRET": ecs.Secret.from_secrets_manager(cognito_secrets, "COGNITO_APP_CLIENT_SECRET")
                    }
                )

                avatar_gallery_container.add_port_mappings(
                    ecs.PortMapping(container_port=8502)
                )

                avatar_services_security_group.add_ingress_rule(
                    peer=avatar_alb_security_group,
                    connection=ec2.Port.tcp(8502),
                    description="Allow traffic from Avatar ALB on port 8502",
                )

                avatar_gallery_service = ecs.FargateService(
                    self,
                    "AvatarGalleryFargateService",
                    service_name="AvatarGalleryService",
                    service_name="AvatarGalleryService",
                    cluster=cluster,
                    task_definition=avatar_gallery_task_definition,
                    desired_count=1,
                    security_groups=[avatar_services_security_group]
                )

                avatar_gallery_target_group = elbv2.ApplicationTargetGroup(
                    self,
                    "AvatarGalleryTargetGroup",
                    port=8502,
                    vpc=vpc,
                    protocol=elbv2.ApplicationProtocol.HTTP,
                    target_type=elbv2.TargetType.IP,
                    health_check=elbv2.HealthCheck(
                        enabled=True,
                        path="/healthz",
                        port="8502",
                        protocol=elbv2.Protocol.HTTP,
                        healthy_http_codes="200",
                        interval=Duration.seconds(30),
                        timeout=Duration.seconds(5),
                        unhealthy_threshold_count=3,
                        healthy_threshold_count=2,
                    )
                )

                avatar_gallery_target_group.add_target(avatar_gallery_service)

                avatar_gallery_rule = elbv2.ApplicationListenerRule(
                    self,
                    "AvatarGalleryRule",
                    listener=avatar_listener,
                    priority=5,
                    conditions=[elbv2.ListenerCondition.host_headers([record_name_avatar_gallery])],
                    action=elbv2.ListenerAction.forward([avatar_gallery_target_group])
                )

        # ################################################
        # NagSuppressions for suppressing findings which
        # are accepted risks for this stack
        # ###############################################
        NagSuppressions.add_resource_suppressions(
            [comfyui_workflow_asg, comfyui_api_asg],
            suppressions=[
                {"id": "AwsSolutions-L1",
                 "reason": "Lambda Runtime is provided by custom resource provider and drain ecs hook implicitely and not critical for sample"
                },
                {"id": "AwsSolutions-SNS2",
                 "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                },
                {"id": "AwsSolutions-SNS3",
                 "reason": "SNS topic is implicitly created by LifeCycleActions and is not critical for sample purposes."
                },
                {"id": "AwsSolutions-AS3",
                 "reason": "Not all scaling notifcations are relevant to be tracked. Because Lambda handles the scaling"
                }
            ],
            apply_to_children=True
        )

        NagSuppressions.add_resource_suppressions_by_path(
            self,
            "/ComfyUIStack/AWS679f53fac002430cb0da5b7982bd2287",
            suppressions=[
                {
                    "id": "AwsSolutions-L1",
                    "reason": "Can not change the runtime of the lambda created behind the construct"
                }
            ]
        )

        NagSuppressions.add_resource_suppressions(
            cognito_secrets,
            suppressions=[
                {
                    "id": "AwsSolutions-SMG4",
                    "reason": "The secret contains cognito environment variables like user-pool id, client_id, client_secret, which are not rotated"
                }
            ]
        )
