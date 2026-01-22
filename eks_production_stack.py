#!/usr/bin/env python3
"""
Production-ready EKS Cluster Stack with AWS CDK

This stack demonstrates best practices for managing EKS clusters:
- Multi-AZ VPC configuration
- Managed node groups
- Karpenter integration
- IRSA (IAM Roles for Service Accounts)
- Core add-ons
- CloudWatch logging
- Security best practices
"""

import aws_cdk as cdk
from aws_cdk import (
    Stack,
    aws_eks as eks,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    Tags,
    Duration,
    RemovalPolicy,
)
from constructs import Construct


class EksProductionStack(Stack):
    """Production-ready EKS cluster with best practices"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ==========================================
        # VPC Configuration
        # ==========================================
        # Create VPC with multi-AZ for high availability
        self.vpc = ec2.Vpc(
            self, "EksVpc",
            max_azs=3,  # Use 3 AZs for high availability
            nat_gateways=2,  # Redundant NAT gateways
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                ),
            ]
        )

        # ==========================================
        # KMS Key for Secrets Encryption
        # ==========================================
        self.eks_secrets_key = kms.Key(
            self, "EksSecretsKey",
            description="KMS key for EKS cluster secrets encryption",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY  # Change for production
        )

        # ==========================================
        # EKS Cluster Configuration
        # ==========================================
        self.cluster = eks.Cluster(
            self, "EksCluster",
            version=eks.KubernetesVersion.V1_29,  # Use latest stable version
            vpc=self.vpc,
            default_capacity=0,  # We'll create node groups manually
            endpoint_access=eks.EndpointAccess.PUBLIC_AND_PRIVATE,  # Security best practice
            vpc_subnets=[
                ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
            ],
            secrets_encryption_key=self.eks_secrets_key,
            cluster_logging=[
                eks.ClusterLoggingTypes.API,
                eks.ClusterLoggingTypes.AUDIT,
                eks.ClusterLoggingTypes.AUTHENTICATOR,
                eks.ClusterLoggingTypes.CONTROLLER_MANAGER,
                eks.ClusterLoggingTypes.SCHEDULER,
            ],
            # Enable control plane logging
        )

        # ==========================================
        # Managed Node Group - General Purpose
        # ==========================================
        self.cluster.add_nodegroup_capacity(
            "GeneralPurposeNodeGroup",
            instance_types=[
                ec2.InstanceType.of(ec2.InstanceClass.M5, ec2.InstanceSize.LARGE),
                ec2.InstanceType.of(ec2.InstanceClass.M5, ec2.InstanceSize.XLARGE),
            ],
            min_size=1,
            max_size=10,
            desired_size=2,
            disk_size=50,
            ami_type=eks.NodegroupAmiType.AL2_X86_64,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            labels={
                "node-type": "general-purpose",
                "environment": "production"
            },
            # Enable automatic updates
            update_config=eks.NodegroupUpdateConfig(
                max_unavailable=1,
                max_unavailable_percentage=25
            ),
        )

        # ==========================================
        # Managed Node Group - Compute Optimized
        # ==========================================
        compute_nodegroup = self.cluster.add_nodegroup_capacity(
            "ComputeOptimizedNodeGroup",
            instance_types=[
                ec2.InstanceType.of(ec2.InstanceClass.C5, ec2.InstanceSize.LARGE),
                ec2.InstanceType.of(ec2.InstanceClass.C5, ec2.InstanceSize.XLARGE),
            ],
            min_size=0,
            max_size=20,
            desired_size=1,
            disk_size=50,
            ami_type=eks.NodegroupAmiType.AL2_X86_64,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            labels={
                "node-type": "compute-optimized",
                "environment": "production"
            },
            taints=[
                eks.TaintSpec(
                    effect=eks.TaintEffect.NO_SCHEDULE,
                    key="workload-type",
                    value="compute-intensive"
                )
            ],
        )

        # ==========================================
        # EKS Add-ons
        # ==========================================
        # VPC CNI Add-on
        self.cluster.add_addon(
            "VpcCni",
            addon_name="vpc-cni",
            version="latest",  # Pin to specific version in production
            resolve_conflicts=eks.AddonResolveConflicts.OVERWRITE,
        )

        # CoreDNS Add-on
        self.cluster.add_addon(
            "CoreDns",
            addon_name="coredns",
            version="latest",
        )

        # kube-proxy Add-on
        self.cluster.add_addon(
            "KubeProxy",
            addon_name="kube-proxy",
            version="latest",
        )

        # EBS CSI Driver Add-on
        ebs_csi_sa = self.cluster.add_service_account(
            "EbsCsiDriverSa",
            name="ebs-csi-driver-sa",
            namespace="kube-system"
        )
        ebs_csi_sa.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonEBSCSIDriverPolicy")
        )

        self.cluster.add_addon(
            "EbsCsiDriver",
            addon_name="aws-ebs-csi-driver",
            version="latest",
            service_account_role=ebs_csi_sa.role,
        )

        # ==========================================
        # Karpenter Setup
        # ==========================================
        # Karpenter Node Role
        karpenter_node_role = iam.Role(
            self, "KarpenterNodeRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSWorkerNodePolicy"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKS_CNI_Policy"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )

        # Tag subnets and security groups for Karpenter discovery
        for subnet in self.vpc.private_subnets:
            Tags.of(subnet).add("karpenter.sh/discovery", self.cluster.cluster_name)
            Tags.of(subnet).add("karpenter.sh/discovery", self.cluster.cluster_name)

        Tags.of(self.cluster.cluster_security_group).add(
            "karpenter.sh/discovery", self.cluster.cluster_name
        )

        # Karpenter Controller Service Account
        karpenter_sa = self.cluster.add_service_account(
            "KarpenterController",
            name="karpenter",
            namespace="karpenter"
        )

        # Karpenter controller permissions
        karpenter_sa.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEKSClusterPolicy")
        )

        karpenter_sa.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:CreateLaunchTemplate",
                    "ec2:CreateFleet",
                    "ec2:RunInstances",
                    "ec2:CreateTags",
                    "iam:PassRole",
                    "ec2:TerminateInstances",
                    "ec2:DescribeLaunchTemplates",
                    "ec2:DescribeInstances",
                    "ec2:DescribeInstanceTypes",
                    "ec2:DescribeInstanceTypeOfferings",
                    "ec2:DescribeAvailabilityZones",
                    "ssm:GetParameter",
                ],
                resources=["*"]
            )
        )

        # Deploy Karpenter via Helm
        self.cluster.add_helm_chart(
            "Karpenter",
            chart="karpenter",
            repository="oci://public.ecr.aws/karpenter/karpenter",
            namespace="karpenter",
            create_namespace=True,
            values={
                "serviceAccount": {
                    "annotations": {
                        "eks.amazonaws.com/role-arn": karpenter_sa.role.role_arn
                    }
                },
                "settings": {
                    "clusterName": self.cluster.cluster_name,
                    "defaultInstanceProfile": karpenter_node_role.role_name,
                }
            }
        )

        # ==========================================
        # Example: IRSA for Application
        # ==========================================
        # Example: Create IAM role for a service account that needs S3 access
        app_service_account_role = iam.Role(
            self, "AppServiceAccountRole",
            assumed_by=iam.WebIdentityPrincipal(
                self.cluster.open_id_connect_provider.open_id_connect_provider_arn
            ).with_conditions({
                "StringEquals": {
                    f"{self.cluster.cluster_open_id_connect_issuer}:sub": "system:serviceaccount:default:app-service-account",
                    f"{self.cluster.cluster_open_id_connect_issuer}:aud": "sts.amazonaws.com"
                }
            }),
            description="IRSA role for application service account"
        )

        # Attach S3 read-only policy (example)
        app_service_account_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3ReadOnlyAccess")
        )

        # Create Kubernetes service account with IRSA annotation
        self.cluster.add_manifest("AppServiceAccount", {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "app-service-account",
                "namespace": "default",
                "annotations": {
                    "eks.amazonaws.com/role-arn": app_service_account_role.role_arn
                }
            }
        })

        # ==========================================
        # IRSA Service Account for ECR Image Pulling
        # ==========================================
        # Create IAM role for service account that needs ECR access
        ecr_service_account_role = iam.Role(
            self, "EcrServiceAccountRole",
            assumed_by=iam.WebIdentityPrincipal(
                self.cluster.open_id_connect_provider.open_id_connect_provider_arn
            ).with_conditions({
                "StringEquals": {
                    f"{self.cluster.cluster_open_id_connect_issuer}:sub": "system:serviceaccount:default:ecr-pull-service-account",
                    f"{self.cluster.cluster_open_id_connect_issuer}:aud": "sts.amazonaws.com"
                }
            }),
            description="IRSA role for ECR image pulling service account"
        )

        # Attach ECR read-only policy for pulling images
        ecr_service_account_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly")
        )

        # Create Kubernetes service account with IRSA annotation
        self.cluster.add_manifest("EcrPullServiceAccount", {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "ecr-pull-service-account",
                "namespace": "default",
                "annotations": {
                    "eks.amazonaws.com/role-arn": ecr_service_account_role.role_arn
                }
            }
        })

        # ==========================================
        # ExternalSecret for ECR Authorization Token
        # ==========================================
        # Create ECRAuthorizationToken generator
        # This generates ECR authorization tokens using IRSA
        self.cluster.add_manifest("EcrAuthTokenGenerator", {
            "apiVersion": "generators.external-secrets.io/v1alpha1",
            "kind": "ECRAuthorizationToken",
            "metadata": {
                "name": "ecr-auth-token-generator",
                "namespace": "default"
            },
            "spec": {
                "region": self.region,
                "auth": {
                    "jwt": {
                        "serviceAccountRef": {
                            "name": "ecr-pull-service-account",
                            "namespace": "default"
                        }
                    }
                }
            }
        })

        # Create ExternalSecret that uses the ECRAuthorizationToken generator
        # This creates a Kubernetes secret with the ECR authorization token
        self.cluster.add_manifest("EcrAuthTokenExternalSecret", {
            "apiVersion": "external-secrets.io/v1beta1",
            "kind": "ExternalSecret",
            "metadata": {
                "name": "ecr-authorization-token",
                "namespace": "default"
            },
            "spec": {
                "refreshInterval": "1h",  # Refresh token every hour (ECR tokens are valid for 12h)
                "target": {
                    "name": "ecr-authorization-token",
                    "creationPolicy": "Owner",
                    "type": "kubernetes.io/dockerconfigjson"
                },
                "dataFrom": [
                    {
                        "sourceRef": {
                            "generatorRef": {
                                "apiVersion": "generators.external-secrets.io/v1alpha1",
                                "kind": "ECRAuthorizationToken",
                                "name": "ecr-auth-token-generator"
                            }
                        }
                    }
                ]
            }
        })

        # Output the service account role ARN
        cdk.CfnOutput(
            self, "EcrServiceAccountRoleArn",
            value=ecr_service_account_role.role_arn,
            description="IAM Role ARN for ECR pull service account"
        )

        # ==========================================
        # Example: Network Policy
        # ==========================================
        # Deny all ingress by default
        self.cluster.add_manifest("DefaultDenyAllNetworkPolicy", {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": "default-deny-all",
                "namespace": "default"
            },
            "spec": {
                "podSelector": {},
                "policyTypes": ["Ingress", "Egress"]
            }
        })

        # ==========================================
        # Example: Pod Security Standards
        # ==========================================
        # Create namespace with pod security standards
        self.cluster.add_manifest("ProductionNamespace", {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "production",
                "labels": {
                    "pod-security.kubernetes.io/enforce": "restricted",
                    "pod-security.kubernetes.io/audit": "restricted",
                    "pod-security.kubernetes.io/warn": "restricted"
                }
            }
        })

        # ==========================================
        # Outputs
        # ==========================================
        cdk.CfnOutput(
            self, "ClusterName",
            value=self.cluster.cluster_name,
            description="EKS Cluster Name"
        )

        cdk.CfnOutput(
            self, "ClusterEndpoint",
            value=self.cluster.cluster_endpoint,
            description="EKS Cluster Endpoint"
        )

        cdk.CfnOutput(
            self, "ClusterSecurityGroupId",
            value=self.cluster.cluster_security_group.security_group_id,
            description="EKS Cluster Security Group ID"
        )

        cdk.CfnOutput(
            self, "KubectlRoleArn",
            value=self.cluster.kubectl_role.role_arn if self.cluster.kubectl_role else "N/A",
            description="IAM Role for kubectl access"
        )

        cdk.CfnOutput(
            self, "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID"
        )

