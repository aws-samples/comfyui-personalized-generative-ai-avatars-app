import json
import os
import boto3
from botocore.exceptions import ClientError

# Initialize AWS clients
asg_client = boto3.client('autoscaling')
ecs_client = boto3.client('ecs')
elbv2_client = boto3.client('elbv2')

def handler(event, context):
    if event['httpMethod'] == 'GET' and not event.get('queryStringParameters'):

        check_and_update_listener_rule()

        # Serve the main HTML page with initial state
        status = get_status()
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/html'},
            'body': get_html_content(status)
        }

    # Handle API calls
    params = event.get('queryStringParameters', {})
    action = params.get('action')
    service = params.get('service')
    direction = params.get('direction')

    if action == 'status':
        result = get_status()
    elif action == 'scale':
        result = scale_service(service, direction)
    elif action == 'restart':
        result = restart_service(service)
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid action'})
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(result)
    }

def get_status():
    try:
        status = {}
        
        # Workflow status
        workflow_asg = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[os.environ['WORKFLOW_ASG_NAME']])['AutoScalingGroups'][0]
        workflow_service = ecs_client.describe_services(
            cluster=os.environ['ECS_CLUSTER_NAME'],
            services=[os.environ['WORKFLOW_SERVICE_NAME']]
        )['services'][0]

        status['workflow'] = {
            'desired': workflow_asg['DesiredCapacity'],
            'running': workflow_service['runningCount'],
            'instances': len(workflow_asg['Instances']),
            'max_capacity': workflow_asg['MaxSize'],
            'min_capacity': workflow_asg['MinSize']
        }

        # API status (only if environment variables are set)
        if os.environ.get('API_ASG_NAME') and os.environ.get('API_SERVICE_NAME'):
            api_asg = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[os.environ['API_ASG_NAME']])['AutoScalingGroups'][0]
            api_service = ecs_client.describe_services(
                cluster=os.environ['ECS_CLUSTER_NAME'],
                services=[os.environ['API_SERVICE_NAME']]
            )['services'][0]
            
            status['api'] = {
                'desired': api_asg['DesiredCapacity'],
                'running': api_service['runningCount'],
                'instances': len(api_asg['Instances']),
                'max_capacity': api_asg['MaxSize'],
                'min_capacity': api_asg['MinSize']
            }

        return status
    except ClientError as e:
        print(f"Error getting status: {e}")
        return {'error': 'Failed to get status'}
def check_and_update_listener_rule():
    try:
        workflow_asg_name = os.environ['WORKFLOW_ASG_NAME']
        ecs_cluster_name = os.environ['ECS_CLUSTER_NAME']
        workflow_service_name = os.environ['WORKFLOW_SERVICE_NAME']
        listener_arn = os.environ.get('LISTENER_ARN')

        if not listener_arn:
            print("LISTENER_RULE_ARN not set in environment variables")
            return

        # Get current ASG state
        asg_response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[workflow_asg_name])
        asg = asg_response['AutoScalingGroups'][0]
        desired_capacity = asg['DesiredCapacity']

        # Check ECS service
        ecs_response = ecs_client.describe_services(
            cluster=ecs_cluster_name,
            services=[workflow_service_name]
        )
        running_count = ecs_response['services'][0]['runningCount']

        # Check conditions
        if desired_capacity == 1 and running_count == 1:
            paginator = elbv2_client.get_paginator('describe_rules')
            page_iterator = paginator.paginate(ListenerArn=listener_arn)

            listener_rule_arn = None

            for page in page_iterator:
                for rule in page['Rules']:
                    for condition in rule.get('Conditions', []):
                        if condition['Field'] == 'path-pattern':
                            if '/admin' in condition['Values']:
                                listener_rule_arn = rule['RuleArn']
                                break
                    if listener_rule_arn:
                        break
                if listener_rule_arn:
                    break

            if not listener_rule_arn:
                raise Exception("Listener rule with path pattern '/admin' not found")

            # Update the listener rule
            elbv2_client.modify_rule(
                RuleArn=listener_rule_arn,
                Conditions=[
                    {
                        'Field': 'path-pattern',
                        'Values': ['/admin']
                    }
                ]
            )
            print("Listener rule updated successfully")
        else:
            print(f"Conditions not met for listener rule update. Desired capacity: {desired_capacity}, Running count: {running_count}")

    except ClientError as e:
        print(f"Error checking or updating listener rule: {e}")

def scale_service(service, direction):
    if service not in ['workflow', 'api']:
        return {'error': 'Invalid service'}
    
    if service == 'api' and not (os.environ.get('API_ASG_NAME') and os.environ.get('API_SERVICE_NAME')):
        return {'error': 'API service is not configured'}

    try:
        asg_name = os.environ[f'{service.upper()}_ASG_NAME']
        ecs_cluster_name = os.environ['ECS_CLUSTER_NAME']
        ecs_service_name = os.environ[f'{service.upper()}_SERVICE_NAME']

        # Get current ASG state
        asg_response = asg_client.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name])
        asg = asg_response['AutoScalingGroups'][0]
        current_capacity = asg['DesiredCapacity']

        # Calculate new capacity
        if direction == 'up':
            new_capacity = min(current_capacity + 1, asg['MaxSize'])
        else:  # 'down'
            new_capacity = max(current_capacity - 1, asg['MinSize'])

        # Update ASG if changed
        if new_capacity != current_capacity:
            asg_client.set_desired_capacity(
                AutoScalingGroupName=asg_name,
                DesiredCapacity=new_capacity
            )

        # Update ECS service
        ecs_client.update_service(
            cluster=ecs_cluster_name,
            service=ecs_service_name,
            desiredCount=new_capacity
        )

        return {'message': f'Scaled {service} to {new_capacity}'}

    except ClientError as e:
        print(f"Error scaling service: {e}")
        return {'error': 'Failed to scale service'}

def restart_service(service):
    if service not in ['workflow', 'api']:
        return {'error': 'Invalid service'}
    
    if service == 'api' and not (os.environ.get('API_ASG_NAME') and os.environ.get('API_SERVICE_NAME')):
        return {'error': 'API service is not configured'}

    try:
        service_name = os.environ[f'{service.upper()}_SERVICE_NAME']
        ecs_client.update_service(
            cluster=os.environ['ECS_CLUSTER_NAME'],
            service=service_name,
            forceNewDeployment=True
        )
        return {'message': f'Restarted {service} service'}
    except ClientError as e:
        print(f"Error restarting service: {e}")
        return {'error': 'Failed to restart service'}


def get_html_content(status):
    api_html = ""
    if 'api' in status:
        api_html = f"""
        <div class="card">
            <h2>ComfyUI API</h2>
            <div id="api-status" class="status">
                <div class="status-item">
                    <p id="api-desired">{status['api']['desired']}</p>
                    <span>Desired Capacity</span>
                </div>
                <div class="status-item">
                    <p id="api-min">{status['api']['min_capacity']}</p>
                    <span>Min Capacity</span>
                </div>
                <div class="status-item">
                    <p id="api-max">{status['api']['max_capacity']}</p>
                    <span>Max Capacity</span>
                </div>
                <div class="status-item">
                    <p id="api-running">{status['api']['running']}</p>
                    <span>Running ECS Tasks</span>
                </div>
                <div class="status-item">
                    <p id="api-instances">{status['api']['instances']}</p>
                    <span>EC2 Instances</span>
                </div>
            </div>
            <div class="controls">
                <button id="api-scaleup" onclick="scaleService('api', 'up')">Scale Up</button>
                <button id="api-scaledown" onclick="scaleService('api', 'down')">Scale Down</button>
                <button class="restart-btn" onclick="restartService('api')">Restart ECS Service</button>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ComfyUI Admin Dashboard</title>
        <style>
            :root {{
                --primary-color: #9575CD;
                --primary-light: #B39DDB;
                --secondary-color: #FF9800;
                --background-color: #121212;
                --card-background: #1E1E1E;
                --text-color: #F1F1F1;
                --disabled-color: #2A2A2A;
            }}
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 0;
                background-color: var(--background-color);
                color: var(--text-color);
            }}
            .container {{
                max-width: 1000px;
                margin: 2rem auto;
                padding: 0 1rem;
            }}
            h1, h2 {{
                color: var(--primary-light);
                text-align: center;
            }}
            .card {{
                background-color: var(--card-background);
                border-radius: 12px;
                box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
                padding: 1.5rem;
                margin-bottom: 2rem;
                border: 1px solid var(--primary-color);
            }}
            .status {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 1rem;
                margin-bottom: 1rem;
            }}
            .status-item {{
                background-color: #2A2A2A;
                padding: 0.75rem;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
            }}
            .status-item p {{
                margin: 0;
                font-weight: bold;
                font-size: 1.2rem;
                color: var(--primary-light);
            }}
            .status-item span {{
                font-size: 0.9rem;
                color: #BDBDBD;
            }}
            .controls {{
                display: flex;
                justify-content: center;
                gap: 1rem;
                margin-top: 1rem;
            }}
            .description {{
                background-color: rgba(94, 53, 177, 0.1);
                padding: 1.5rem;
                margin-bottom: 1rem;
                border-radius: 8px;
                text-align: center;
            }}
            
            .description p {{
                margin: 0 0 0.5rem 0;
                line-height: 1.6;
                font-size: 1.1rem;
            }}

            .caution {{
                font-style: italic;
                color: #FFA000;
                font-size: 1.2rem;
                font-weight: bold;
            }}
            button {{
                background-color: var(--primary-color);
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 6px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-weight: bold;
            }}
            button:hover {{
                background-color: var(--primary-light);
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            }}
            button:disabled {{
                background-color: var(--disabled-color);
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }}
            .restart-btn {{
                background-color: var(--secondary-color);
            }}
            .restart-btn:hover {{
                background-color: #FFB300;
            }}

            .button-container {{
                display: flex;
                justify-content: center;
                gap: 1rem;
                margin-top: 1rem;
            }}

            #magic-button {{
                background-color: #00695C;
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 6px;
                cursor: pointer;
                font-weight: bold;
                transition: all 0.3s ease;
            }}

            #magic-button:hover {{
                background-color: #00897B;
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            }}

        </style>
    </head>
    <body>
        <div class="container">
            <h1>ComfyUI Admin Dashboard</h1>
            <div class="description">
                <p>This dashboard allows you to monitor and manage your ComfyUI infrastructure on AWS. You can view the status of your workflow and API instances, scale services, and restart ECS services as needed.</p>
                <p class="caution">⚠️ Caution: Think twice before making changes. Actions taken here directly affect your live infrastructure.</p>
            </div>
            <div class="card">
                <h2>ComfyUI Workflow</h2>
                <div id="workflow-status" class="status">
                    <div class="status-item">
                        <p id="workflow-desired">{status['workflow']['desired']}</p>
                        <span>Desired Capacity</span>
                    </div>
                    <div class="status-item">
                        <p id="workflow-min">{status['workflow']['min_capacity']}</p>
                        <span>Min Capacity</span>
                    </div>
                    <div class="status-item">
                        <p id="workflow-max">{status['workflow']['max_capacity']}</p>
                        <span>Max Capacity</span>
                    </div>
                    <div class="status-item">
                        <p id="workflow-running">{status['workflow']['running']}</p>
                        <span>Running ECS Tasks</span>
                    </div>
                    <div class="status-item">
                        <p id="workflow-instances">{status['workflow']['instances']}</p>
                        <span>EC2 Instances</span>
                    </div>
                </div>
                <div class="controls">
                    <button id="workflow-scaleup" onclick="scaleService('workflow', 'up')">Scale Up</button>
                    <button id="workflow-scaledown" onclick="scaleService('workflow', 'down')">Scale Down</button>
                    <button class="restart-btn" onclick="restartService('workflow')">Restart ECS Service</button>
                </div>
            </div>
            
            {api_html}

            <div class="button-container">
                <button id="refresh-button" onclick="fetchStatus()">Refresh Status</button>
                <a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ" target="_blank" rel="noopener noreferrer">
                    <button id="magic-button">Magic Button</button>
                </a>
            </div>
            </div>
        </div>

        <script>
        async function fetchStatus() {{
            try {{
                const response = await fetch('?action=status');
                const status = await response.json();
                updateStatus(status);
            }} catch (error) {{
                console.error('Error fetching status:', error);
            }}
        }}

        function updateStatus(status) {{
            for (const [service, data] of Object.entries(status)) {{
                for (const [key, value] of Object.entries(data)) {{
                    const element = document.getElementById(`${{service}}-${{key}}`);
                    if (element) {{
                        element.textContent = value;
                    }}
                }}
                
                const scaleUpBtn = document.getElementById(`${{service}}-scaleup`);
                const scaleDownBtn = document.getElementById(`${{service}}-scaledown`);
                
                if (scaleUpBtn && scaleDownBtn) {{
                    scaleUpBtn.disabled = data.instances >= data.max_capacity;
                    scaleDownBtn.disabled = data.instances <= data.min_capacity;
                }}
            }}
        }}

        async function scaleService(service, direction) {{
            const statusElement = document.getElementById(`${{service}}-instances`);
            const maxElement = document.getElementById(`${{service}}-max`);
            const minElement = document.getElementById(`${{service}}-min`);
            
            if (!statusElement || !maxElement || !minElement) return;
            
            const currentInstances = parseInt(statusElement.textContent);
            const maxCapacity = parseInt(maxElement.textContent);
            const minCapacity = parseInt(minElement.textContent);

            if ((direction === 'up' && currentInstances >= maxCapacity) ||
                (direction === 'down' && currentInstances <= minCapacity)) {{
                alert(`Cannot scale ${{direction}}. Current instances: ${{currentInstances}}, Min: ${{minCapacity}}, Max: ${{maxCapacity}}`);
                return;
            }}

            try {{
                const response = await fetch(`?action=scale&service=${{service}}&direction=${{direction}}`);
                const result = await response.json();
                alert(result.message || result.error);
                fetchStatus();
            }} catch (error) {{
                console.error('Error scaling service:', error);
                alert('Failed to scale service. Check console for details.');
            }}
        }}

        async function restartService(service) {{
            try {{
                const response = await fetch(`?action=restart&service=${{service}}`);
                const result = await response.json();
                alert(result.message || result.error);
                fetchStatus();
            }} catch (error) {{
                console.error('Error restarting service:', error);
                alert('Failed to restart service. Check console for details.');
            }}
        }}

        // Initial status update
        fetchStatus();
        </script>
    </body>
    </html>
    """

