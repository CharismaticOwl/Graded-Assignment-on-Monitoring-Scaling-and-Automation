# import boto3 Amazon SDK and time
import boto3
import time

# defining variable for region of choice
REGION='ap-south-1'

# --> Step 1: Web Application Deployment 

# Create an S3 client
s3_client = boto3.client('s3')

# defining function to create an s3 bucket with handling errors gracefully
def create_s3_bucket(bucket_name):

    # try block to attempt creating a bucket
    try:
        s3_client.create_bucket(Bucket=bucket_name,
                         CreateBucketConfiguration={
                            'LocationConstraint': REGION,
                            }
                        )
        # return bucket created text if the create_bucket was successful
        return f"S3 bucket '{bucket_name}' created successfully."
    
    # If any exception, like bucket name already exists or if bucket is already owned by us
    except Exception as e:
        return f"An error occurred: {str(e)}"

# defning bucket name in a vatiable
bucket_name = 'web-application-static-files-1'

# calling the create bucket function
result_message = create_s3_bucket(bucket_name)

# printing the return value for the create bucket function
print(result_message)

# defining function to upload to s3 bucket with handling errors gracefully
def upload_to_s3_bucket(bucket_name):
    # try block to attempt upload file a bucket
    try:
        s3_client.upload_file('index.html',bucket_name, 'index.html')
        return f"File index.html has been uploaded successfully."
    # if eny exception, return the exception as a string
    except Exception as e:
        return f"An error occurred: {str(e)}"

# sotring the response from upload to s3 function
result_message_upload_to_s3 = upload_to_s3_bucket(bucket_name)

# printing the response from upload to s3 function
print(result_message_upload_to_s3)

# Create an ec2 client

ec2_client = boto3.client('ec2', region_name=REGION)

# Defining USERDATA and other variables to store the bash script and also instance details to be launched
USERDATA='''#!/bin/bash
sudo apt update
sudo apt install awscli nginx -y
aws s3 cp s3://web-application-static-files-1/index.html /tmp/index.html
sudo systemctl start nginx
sudo systemctl enable nginx
sudo rm -rf /var/www/html/*
sudo cp /tmp/index.html /var/www/html/index.html
sudo systemctl restart nginx
'''
AMI_IMAGE_ID = 'ami-03f4878755434977f'
INSTANCE_TYPE = 't2.micro'
DISK_SIZE_GB = 8
DEVICE_NAME = '/dev/xvda'
security_groups = ['sg-09e0c5dd41f4bd5b9']
# ec2 role, so that s3 bucket can be access from the instance that will be created
ROLE_PROFILE = 'ec2-service-role-admin'

# empty list to store the instance id that will get generated
InstanceIds=[]

# defining function to create an ec2 Instance with handling errors gracefully

def create_ec2_instance():
    # Try block to attempt running an instance
    try:
        response = ec2_client.run_instances(
            ImageId=AMI_IMAGE_ID,
            InstanceType=INSTANCE_TYPE,
            SecurityGroupIds=security_groups,
            UserData=USERDATA,
            IamInstanceProfile={
                'Name':ROLE_PROFILE
            },
            TagSpecifications=[
                {
                    'ResourceType': 'instance', 
                    'Tags': [
                        {
                            'Key': 'key',
                            'Value': 'assignment'
                        },
                    ]
                },
            ],
            KeyName='ec2',
            MaxCount=1,
            MinCount=1,
        )

        # If the instance creation is successful, then retrieve the instance id and store it in the empty list for future use
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            instance_id = response['Instances'][0]['InstanceId']
            ec2_client.get_waiter('instance_running').wait(
                InstanceIds.append(instance_id)
            )
            print('Success! instance:', instance_id, 'is created and running')
        # if the response is not 200, then print and raise and exception.
        else:
            print('Error! Failed to create instance!')
            raise Exception('Failed to create instance!')
        return response
    # If any exception, print the exception as string
    except Exception as e:
        return f"An error occurred: {str(e)}"
    
# calling the create ec2 function
create_ec2_instance()

time.sleep(100)

# --> Step 2: Load Balancing with ELB

# Create an elb client
elb_client = boto3.client('elbv2', region_name=REGION)

# defining ALB attributes

alb_name = "assignment-alb"
subnets = ['subnet-05a15ce69d2d9f69d','subnet-076051ff9276a558d','subnet-0564d17c714b6a55a']

# defining empty list to store the target arn's
target_group_arns = []

# defining function which will create load balancer, target group, register targets and add a listener to the ALB

def create_alb_and_attach_ec2():

    # defining target_group attributes

    target_group_name = 'assignment-target-group'
    target_port = 80
    health_check_path = '/'
    protocol = 'HTTP'

    # create_target_group to create the target group
    response_target_grp = elb_client.create_target_group(
        Name=target_group_name,
        Protocol=protocol,
        Port=target_port,
        VpcId='vpc-04ef1d2345f3f906e',
        HealthCheckProtocol=protocol,
        HealthCheckPath=health_check_path,
        HealthCheckPort=str(target_port),
        HealthCheckIntervalSeconds=30,
        HealthCheckTimeoutSeconds=5,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=2,
        Matcher={'HttpCode': '200'}
    )

    # extracting the target group ARN's 
    target_group_arn = response_target_grp['TargetGroups'][0]['TargetGroupArn']

    # append the target group arn to an empty list to use it in future
    target_group_arns.append(target_group_arn)

    print("Target groups created are: ", target_group_arns)

    # create alb

    # using create_load_balancer to create ALB with some tags
    response_alb = elb_client.create_load_balancer(
        Name = alb_name,
        Subnets = subnets,
        SecurityGroups=security_groups,
        Scheme='internet-facing',
        Tags=[{'Key':'Name','Value':alb_name}]
    )

    # Extracting the ARN of the created ALB

    # extracting the load balancer ARN

    alb_arn = response_alb['LoadBalancers'][0]['LoadBalancerArn']

    # Register ec2 instance with the target

    elb_client.register_targets(
        TargetGroupArn=target_group_arn,
        Targets=[{'Id': instance} for instance in InstanceIds]
    )

    # Create a listener for the ALB

    listener_port = 80

    elb_client.create_listener(
        DefaultActions=[{
            'Type': 'forward',
            'TargetGroupArn': target_group_arn
        }],
        LoadBalancerArn=alb_arn,
        Port=listener_port,
        Protocol=protocol
    )

    return f"ALB {alb_name} and Target Group {target_group_name} created successfully."

print(create_alb_and_attach_ec2())

# --> Step 3: Auto Scaling Group (ASG) Configuration

autoscaling_grp_arns = []

# Create an autoscaling client

autoscaling_client = boto3.client('autoscaling',region_name=REGION)

cloudwatch_client = boto3.client('cloudwatch', region_name=REGION)

def create_autoscaling():
    autoscaling_client = boto3.client('autoscaling',region_name=REGION)

    autoscaling_client.create_auto_scaling_group(
        AutoScalingGroupName='assigment_autoscaling_grp',
        # LaunchConfigurationName='assignment_lauch_config',
        MinSize=1,
        MaxSize=2,
        DesiredCapacity=1,
        InstanceId=InstanceIds[0],
        TargetGroupARNs=target_group_arns
    )

    time.sleep(120)

    response_describe_auto_scaling = autoscaling_client.describe_auto_scaling_groups(
        AutoScalingGroupNames=[
            'assigment_autoscaling_grp',
        ]
    )

    asg_arn = response_describe_auto_scaling['AutoScalingGroups'][0]['AutoScalingGroupARN']

    autoscaling_grp_arns.append(asg_arn)

    print(autoscaling_grp_arns)

    # Scale out policy

    autoscaling_client.put_scaling_policy(
        AutoScalingGroupName='assigment_autoscaling_grp',
        PolicyName='ScaleOutPolicy',
        PolicyType='SimpleScaling',
        AdjustmentType='ChangeInCapacity',
        ScalingAdjustment=1,
        Cooldown=300,  # 5 minutes
    )

    # Scale in policy

    autoscaling_client.put_scaling_policy(
        AutoScalingGroupName='assigment_autoscaling_grp',
        PolicyName='ScaleInPolicy',
        PolicyType='SimpleScaling',
        AdjustmentType='ChangeInCapacity',
        ScalingAdjustment=-1,
        Cooldown=300,  # 5 minutes
    )

    print("Auto Scaling Group and Scaling Policies created successfully.")

    return "autoscaling is created"

print(create_autoscaling())

# --> creating S# bucket and uploading the lambda code

def create_s3_bucket(bucket_name):

    # try block to attempt creating a bucket
    try:
        s3_client.create_bucket(Bucket=bucket_name,
                         CreateBucketConfiguration={
                            'LocationConstraint': REGION,
                            }
                        )
        # return bucket created text if the create_bucket was successful
        return f"S3 bucket '{bucket_name}' created successfully."
    
    # If any exception, like bucket name already exists or if bucket is already owned by us
    except Exception as e:
        return f"An error occurred: {str(e)}"

# defning bucket name in a vatiable
bucket_name = 'assignment-bucket-for-lambda-function-storing-712'

# calling the create bucket function
result_message = create_s3_bucket(bucket_name)

# printing the return value for the create bucket function
print(result_message)

# defining function to upload to s3 bucket with handling errors gracefully
def upload_to_s3_bucket(bucket_name):
    # try block to attempt upload file a bucket
    try:
        s3_client.upload_file('lambda.py',bucket_name, 'lambda.py')
        return f"File index.html has been uploaded successfully."
    # if eny exception, return the exception as a string
    except Exception as e:
        return f"An error occurred: {str(e)}"

# sotring the response from upload to s3 function
result_message_upload_to_s3 = upload_to_s3_bucket(bucket_name)

# printing the response from upload to s3 function
print(result_message_upload_to_s3)


# --> Step 4:Lambda-based Health Checks & Management

lambda_client = boto3.client('lambda')

response_lambda = lambda_client.create_function(
    FunctionName = 'Lambda-Health-Checks',
    Runtime = 'python3.9',
    Role = 'Lambda_for_assignment-role-difp8zc1',
    Timeout = 120,
    Code={
        'S3Bucket': 'assignment-bucket-for-lambda-function-storing-712',
        'S3Key': 'lambda.py'
    },
)