import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class StarRatingBreakdown(BaseModel):
    star_5: int = 0
    star_4: int = 0
    star_3: int = 0
    star_2: int = 0
    star_1: int = 0

class CSATSummary(BaseModel):
    average_score: float = Field(default=5.0, description="Average CSAT score out of 5.0")
    total_feedback_count: int = Field(default=0, description="Total number of submitted customer ratings")
    positive_percentage: float = Field(default=100.0, description="Percentage of 4-star and 5-star ratings")
    stars: StarRatingBreakdown = Field(default_factory=StarRatingBreakdown)

class AIResolutionSummary(BaseModel):
    total_conversations: int = 0
    ai_autonomous_count: int = 0
    ai_autonomous_rate: float = 0.0 # Percentage (e.g. 74.5%)
    human_handover_count: int = 0
    human_handover_rate: float = 0.0
    active_now_count: int = 0
    estimated_hours_saved: float = 0.0 # e.g. 125.4 hours

class SpeedMetricsSummary(BaseModel):
    avg_ai_first_response_ms: int = 420
    avg_human_response_seconds: int = 150
    avg_resolution_time_minutes: float = 8.5
    sla_compliance_rate: float = 98.4

class SentimentSummary(BaseModel):
    positive_rate: float = 78.0
    neutral_rate: float = 16.0
    negative_rate: float = 6.0

class AgentPerformanceItem(BaseModel):
    agent_id: uuid.UUID
    name: str
    email: str
    department: str
    assigned_count: int = 0
    resolved_count: int = 0
    avg_csat: float = 5.0
    avg_response_speed_seconds: int = 120
    is_online: bool = False

class DailyTrendPoint(BaseModel):
    date: str
    conversations: int
    ai_resolved: int
    avg_csat: float

class RecentFeedbackItem(BaseModel):
    conversation_id: uuid.UUID
    visitor_name: str
    rating: int
    feedback: Optional[str] = None
    department: str
    created_at: datetime

class AnalyticsOverviewResponse(BaseModel):
    time_range: str # "7d", "30d", "90d"
    csat: CSATSummary
    resolution: AIResolutionSummary
    speed: SpeedMetricsSummary
    sentiment: SentimentSummary
    agent_leaderboard: List[AgentPerformanceItem]
    daily_trends: List[DailyTrendPoint]
    recent_feedback: List[RecentFeedbackItem]

class CSATSubmitPayload(BaseModel):
    rating: int = Field(ge=1, le=5, description="CSAT star rating between 1 and 5")
    feedback: Optional[str] = Field(default=None, max_length=500)
