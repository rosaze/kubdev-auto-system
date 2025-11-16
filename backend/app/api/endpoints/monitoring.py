"""
Monitoring API Endpoints
모니터링 및 메트릭 API
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.environment import EnvironmentInstance
from app.models.resource_metrics import ResourceMetric
from app.services.kubernetes_service import KubernetesService

router = APIRouter()


@router.get("/environments/{environment_id}/metrics")
async def get_environment_metrics(
    environment_id: int,
    hours: int = Query(1, ge=1, le=168, description="Time range in hours (max 7 days)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 환경의 리소스 메트릭 조회"""

    # 환경 존재 및 권한 확인
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # 권한 체크 (본인 환경 또는 admin)
    if environment.user_id != current_user.id and current_user.role.value not in ["org_admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="No permission to access this environment")

    try:
        # 시간 범위 계산
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        # 데이터베이스에서 메트릭 조회
        metrics = db.query(ResourceMetric).filter(
            ResourceMetric.environment_id == environment_id,
            ResourceMetric.timestamp >= start_time,
            ResourceMetric.timestamp <= end_time
        ).order_by(ResourceMetric.timestamp.desc()).all()

        # K8s에서 실시간 상태도 조회
        k8s_service = KubernetesService()
        live_metrics = await k8s_service.get_live_resource_metrics(environment.k8s_namespace)

        # 메트릭 데이터 포맷
        metric_data = []
        for metric in metrics:
            metric_data.append({
                "timestamp": metric.timestamp,
                "cpu_usage_percent": metric.cpu_usage_percent,
                "memory_usage_percent": metric.memory_usage_percent,
                "storage_usage_percent": metric.storage_usage_percent,
                "cpu_usage_millicores": metric.cpu_usage_millicores,
                "memory_usage_mb": metric.memory_usage_mb,
                "storage_usage_gb": metric.storage_usage_gb,
                "network_rx_bytes": metric.network_rx_bytes,
                "network_tx_bytes": metric.network_tx_bytes
            })

        return {
            "environment_id": environment_id,
            "environment_name": environment.name,
            "time_range_hours": hours,
            "data_points": len(metric_data),
            "metrics": metric_data,
            "live_status": live_metrics,
            "resource_limits": {
                "cpu_limit": environment.template.resource_limits.get("cpu", "1000m"),
                "memory_limit": environment.template.resource_limits.get("memory", "2Gi"),
                "storage_limit": environment.template.resource_limits.get("storage", "10Gi")
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/user/{user_id}/environments")
async def get_user_environments_status(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """특정 사용자의 모든 환경 상태 조회"""

    # 권한 체크 (본인 또는 admin)
    if user_id != current_user.id and current_user.role.value not in ["org_admin", "super_admin", "team_leader"]:
        raise HTTPException(status_code=403, detail="No permission to access this user's environments")

    try:
        # 해당 사용자의 환경들 조회
        environments = db.query(EnvironmentInstance).filter(
            EnvironmentInstance.user_id == user_id
        ).all()

        if not environments:
            return {
                "user_id": user_id,
                "total_environments": 0,
                "environments": []
            }

        # 각 환경의 K8s 상태 조회
        k8s_service = KubernetesService()
        environment_statuses = []

        for env in environments:
            try:
                # K8s 상태 조회
                k8s_status = await k8s_service.get_deployment_status(
                    namespace=env.k8s_namespace,
                    deployment_name=env.k8s_deployment_name
                )

                # ResourceQuota 상태 조회
                quota_name = f"quota-{env.k8s_deployment_name}"
                quota_status = await k8s_service.get_resource_quota_status(
                    namespace=env.k8s_namespace,
                    quota_name=quota_name
                )

                environment_statuses.append({
                    "environment_id": env.id,
                    "name": env.name,
                    "status": env.status.value,
                    "k8s_status": k8s_status,
                    "resource_quota": quota_status,
                    "access_url": env.access_url,
                    "created_at": env.created_at,
                    "expires_at": env.expires_at,
                    "template_name": env.template.name if env.template else "unknown"
                })

            except Exception as env_error:
                # 개별 환경 오류는 기록하고 계속
                environment_statuses.append({
                    "environment_id": env.id,
                    "name": env.name,
                    "status": "error",
                    "error": str(env_error),
                    "created_at": env.created_at
                })

        return {
            "user_id": user_id,
            "total_environments": len(environments),
            "active_environments": sum(1 for env in environment_statuses
                                     if env.get("status") == "running"),
            "environments": environment_statuses,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user environments: {str(e)}")


@router.get("/health")
async def health_check():
    """시스템 헬스체크"""
    try:
        # K8s 연결 상태 확인
        k8s_service = KubernetesService()
        cluster_info = await k8s_service.get_cluster_overview()

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": {
                "database": "connected",
                "kubernetes": "connected",
                "api": "running"
            },
            "cluster_info": {
                "total_nodes": cluster_info["cluster_info"]["total_nodes"],
                "ready_nodes": cluster_info["cluster_info"]["ready_nodes"],
                "total_pods": cluster_info["cluster_info"]["total_pods"]
            }
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e),
            "services": {
                "database": "unknown",
                "kubernetes": "error",
                "api": "running"
            }
        }


@router.get("/metrics/system")
async def get_system_metrics(
    current_user: User = Depends(get_current_user)
):
    """시스템 전체 메트릭"""
    try:
        k8s_service = KubernetesService()

        # 클러스터 전체 현황
        cluster_overview = await k8s_service.get_cluster_overview()

        # 모든 KubeDev 환경 상태
        all_environments = await k8s_service.get_all_environments_status()

        # 메트릭 집계
        metrics = {
            "cluster": cluster_overview,
            "environments": {
                "total": len(all_environments),
                "running": sum(1 for env in all_environments if env["status"] == "Running"),
                "pending": sum(1 for env in all_environments if env["status"] == "Pending"),
                "failed": sum(1 for env in all_environments if env["status"] == "Failed")
            },
            "resource_utilization": {
                "total_quotas": 0,
                "avg_cpu_usage": 0,
                "avg_memory_usage": 0,
                "high_usage_environments": 0
            }
        }

        # ResourceQuota 사용률 계산
        quota_data = []
        for env in all_environments:
            if env.get("resource_quota"):
                quota = env["resource_quota"]
                if quota.get("utilization"):
                    cpu_util = quota["utilization"].get("cpu_percent", 0)
                    mem_util = quota["utilization"].get("memory_percent", 0)

                    quota_data.append({
                        "cpu_usage": cpu_util,
                        "memory_usage": mem_util
                    })

                    # 높은 사용률 환경 카운트 (80% 이상)
                    if cpu_util > 80 or mem_util > 80:
                        metrics["resource_utilization"]["high_usage_environments"] += 1

        if quota_data:
            metrics["resource_utilization"]["total_quotas"] = len(quota_data)
            metrics["resource_utilization"]["avg_cpu_usage"] = round(
                sum(q["cpu_usage"] for q in quota_data) / len(quota_data), 2
            )
            metrics["resource_utilization"]["avg_memory_usage"] = round(
                sum(q["memory_usage"] for q in quota_data) / len(quota_data), 2
            )

        return {
            "metrics": metrics,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system metrics: {str(e)}")


@router.get("/logs/{environment_id}")
async def get_environment_logs(
    environment_id: int,
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines"),
    follow: bool = Query(False, description="Follow log stream"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """환경 로그 조회"""

    # 환경 존재 및 권한 확인
    environment = db.query(EnvironmentInstance).filter(
        EnvironmentInstance.id == environment_id
    ).first()

    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # 권한 체크
    if environment.user_id != current_user.id and current_user.role.value not in ["org_admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="No permission to access this environment")

    try:
        k8s_service = KubernetesService()

        logs = await k8s_service.get_pod_logs(
            namespace=environment.k8s_namespace,
            deployment_name=environment.k8s_deployment_name,
            tail_lines=lines
        )

        return {
            "environment_id": environment_id,
            "environment_name": environment.name,
            "logs": logs,
            "lines_requested": lines,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")


@router.get("/alerts")
async def get_user_alerts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """사용자별 알림 조회"""

    try:
        alerts = []

        # 사용자의 환경들 조회
        user_environments = db.query(EnvironmentInstance).filter(
            EnvironmentInstance.user_id == current_user.id
        ).all()

        for env in user_environments:
            # 만료 임박 알림
            if env.expires_at:
                time_until_expiry = env.expires_at - datetime.utcnow()
                if time_until_expiry <= timedelta(hours=1) and time_until_expiry > timedelta(0):
                    alerts.append({
                        "type": "warning",
                        "category": "expiration",
                        "message": f"Environment '{env.name}' will expire in {time_until_expiry}",
                        "environment_id": env.id,
                        "expires_at": env.expires_at
                    })

            # 오류 상태 알림
            if env.status.value == "error":
                alerts.append({
                    "type": "error",
                    "category": "environment_error",
                    "message": f"Environment '{env.name}' is in error state",
                    "environment_id": env.id,
                    "status_message": env.status_message
                })

        return {
            "user_id": current_user.id,
            "alerts": alerts,
            "total": len(alerts),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alerts: {str(e)}")