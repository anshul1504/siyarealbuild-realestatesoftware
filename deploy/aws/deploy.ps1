param(
    [Parameter(Mandatory = $true)][string]$Region,
    [Parameter(Mandatory = $true)][string]$Repository,
    [Parameter(Mandatory = $true)][string]$StackName,
    [Parameter(Mandatory = $true)][string]$ParameterFile
)

$ErrorActionPreference = "Stop"
$account = aws sts get-caller-identity --query Account --output text
$registry = "$account.dkr.ecr.$Region.amazonaws.com"
$image = "$registry/$Repository`:$(git rev-parse --short HEAD)"

aws ecr describe-repositories --region $Region --repository-names $Repository 2>$null
if ($LASTEXITCODE -ne 0) {
    aws ecr create-repository --region $Region --repository-name $Repository | Out-Null
}

aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin $registry
docker build -t $image .
docker push $image

aws cloudformation deploy `
    --region $Region `
    --stack-name $StackName `
    --template-file deploy/aws/infrastructure.yml `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides "file://$ParameterFile" "ImageUri=$image"

$cluster = aws cloudformation describe-stacks --region $Region --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='ClusterName'].OutputValue" --output text
$taskDefinition = aws cloudformation describe-stacks --region $Region --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='TaskDefinitionArn'].OutputValue" --output text
$subnets = aws ecs describe-services --region $Region --cluster $cluster --services (aws cloudformation describe-stacks --region $Region --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='ServiceName'].OutputValue" --output text) --query "services[0].networkConfiguration.awsvpcConfiguration.subnets" --output text
$securityGroups = aws ecs describe-services --region $Region --cluster $cluster --services (aws cloudformation describe-stacks --region $Region --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='ServiceName'].OutputValue" --output text) --query "services[0].networkConfiguration.awsvpcConfiguration.securityGroups" --output text
$network = "awsvpcConfiguration={subnets=[$(($subnets -split '\s+') -join ',' )],securityGroups=[$(($securityGroups -split '\s+') -join ',' )],assignPublicIp=ENABLED}"

foreach ($command in @("python manage.py migrate", "python manage.py check --deploy")) {
    $override = "{`"containerOverrides`":[{`"name`":`"app`",`"command`":[`"sh`",`"-c`",`"$command`"]}]}"
    $task = aws ecs run-task --region $Region --cluster $cluster --launch-type FARGATE --task-definition $taskDefinition --network-configuration $network --overrides $override --query "tasks[0].taskArn" --output text
    aws ecs wait tasks-stopped --region $Region --cluster $cluster --tasks $task
    $exitCode = aws ecs describe-tasks --region $Region --cluster $cluster --tasks $task --query "tasks[0].containers[0].exitCode" --output text
    if ($exitCode -ne "0") { throw "Deployment task failed: $command" }
}

aws ecs update-service --region $Region --cluster $cluster --service (aws cloudformation describe-stacks --region $Region --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='ServiceName'].OutputValue" --output text) --force-new-deployment | Out-Null
aws ecs wait services-stable --region $Region --cluster $cluster --services (aws cloudformation describe-stacks --region $Region --stack-name $StackName --query "Stacks[0].Outputs[?OutputKey=='ServiceName'].OutputValue" --output text)
