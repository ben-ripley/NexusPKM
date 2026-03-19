"""Microsoft Graph API shared package."""

from nexuspkm.connectors.ms_graph.auth import (
    AuthFlowContext,
    DeviceCodeInfo,
    DeviceFlowDict,
    MicrosoftGraphAuth,
)
from nexuspkm.connectors.ms_graph.teams import TeamsTranscriptConnector
from nexuspkm.connectors.ms_graph.vtt_parser import (
    ParsedTranscript,
    TranscriptSegment,
    parse_vtt,
)

__all__ = [
    "AuthFlowContext",
    "DeviceCodeInfo",
    "DeviceFlowDict",
    "MicrosoftGraphAuth",
    "ParsedTranscript",
    "TeamsTranscriptConnector",
    "TranscriptSegment",
    "parse_vtt",
]
