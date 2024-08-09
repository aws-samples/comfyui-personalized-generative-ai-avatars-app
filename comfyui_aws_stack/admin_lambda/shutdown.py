import json
import boto3
import os

def handler(event, context):
    asg_name = os.environ.get("ASG_NAME")
    ecs_cluster_name = os.environ.get("ECS_CLUSTER_NAME")
    ecs_service_name = os.environ.get("ECS_SERVICE_NAME")

    # Validate environment variables
    if not all([asg_name, ecs_cluster_name, ecs_service_name]):
        return {
            'statusCode': 400,
            'body': json.dumps('Missing required environment variables')
        }

    # Clients
    asg_client = boto3.client('autoscaling')
    ecs_client = boto3.client('ecs')

    try:
        # Update the ECS service to have 0 desired count
        ecs_client.update_service(
            cluster=ecs_cluster_name,
            service=ecs_service_name,
            desiredCount=0
        )

        # Update the desired capacity of the ASG
        asg_client.set_desired_capacity(
            AutoScalingGroupName=asg_name,
            DesiredCapacity=0,
            HonorCooldown=False
        )

        message = "ComfyUI is shutting down"
    except Exception as e:
        print(f"Error: {e}")
        message = "Error occurred. Unable to scale ComfyUI."

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="X-UA-Compatible" content="ie=edge">
        <!-- <meta http-equiv="refresh" content="0; URL=https://www.youtube.com/watch?v=dQw4w9WgXcQ" /> -->
        <title>ComfyUI Shutdown</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #202020;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                color: #333;
            }}
            main {{
                text-align: center;
                background-color: #ffffff;
                padding: 40px;
                border-radius: 5px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                max-width: 600px;
            }}
            h1 {{
                margin-bottom: 20px;
            }}
            p {{
                margin-bottom: 30px;
            }}
            .video-link {{
                display: inline-block;
                background-color: #54646f;
                color: white;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 2px;
                transition: background-color 0.3s ease;
            }}
            .video-link:hover {{
                background-color: #005fa3;
            }}
        </style>
    </head>
    <body>
        <main>
            <h1>{message}</h1>
        </main>
    </body>
    </html>
    """

    return {"statusCode": 200, "body": html, "headers": {"Content-Type": "text/html"}}


