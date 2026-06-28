using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using NewsMarketAgent.Api.Data;
using NewsMarketAgent.Api.Models;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/prices")]
public class PricesController(AppDbContext db) : ControllerBase
{
    [HttpGet("{ticker}")]
    public async Task<IEnumerable<PriceResponseDto>> Get(string ticker, [FromQuery] int days = 30)
    {
        var cutoff = DateOnly.FromDateTime(DateTime.UtcNow.AddDays(-days));

        return await db.Prices
            .Where(p => p.Ticker == ticker.ToUpper() && p.Date >= cutoff)
            .OrderBy(p => p.Date)
            .Select(p => new PriceResponseDto
            {
                Ticker = p.Ticker,
                Date   = p.Date.ToString("yyyy-MM-dd"),
                Close  = p.Close,
            })
            .ToListAsync();
    }
}
