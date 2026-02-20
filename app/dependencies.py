from dotenv import load_dotenv
load_dotenv()

from app.services.campus_registry import CampusRegistry
from app.services.ghl_service import GHLService
from app.services.apify_service import ApifyService
from app.services.conversation_service import ConversationService
from app.services.advisor_service import AdvisorService
from app.services.lead_state_service import LeadStateService
from app.services.objection_service import ObjectionService
from app.services.orchestrator_service import ConversationOrchestrator
from app.tools.objection_tools import init_objection_tool

# Initialize Singletons
campus_registry = CampusRegistry()
ghl_service = GHLService(campus_registry)
apify_service = ApifyService()
conversation_service = ConversationService()
advisor_service = AdvisorService(campus_registry)
lead_state_service = LeadStateService()
objection_service = ObjectionService()

# Orchestrator (conversations pipeline)
orchestrator = ConversationOrchestrator(
    ghl_service=ghl_service,
    conversation_service=conversation_service,
    advisor_service=advisor_service,
    lead_state_service=lead_state_service,
    campus_registry=campus_registry,
)

# Inject objection service into the LangChain tool
init_objection_tool(objection_service)
