"""법원경매 데이터 수집기 · SIONLAB."""
from .service import AuctionService
from .models import AuctionError
__version__='0.2.1'
__all__=['AuctionService','AuctionError']
