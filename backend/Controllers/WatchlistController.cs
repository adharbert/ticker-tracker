using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Models;
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/watchlist")]
public class WatchlistController(IWatchlistService watchlist) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll() =>
        Ok(await watchlist.GetAllAsync());

    [HttpPost]
    public async Task<IActionResult> Add([FromBody] AddWatchlistItemDto dto)
    {
        if (string.IsNullOrWhiteSpace(dto.Ticker))
            return BadRequest(new { message = "Ticker is required." });

        await watchlist.AddAsync(dto with { Ticker = dto.Ticker.ToUpperInvariant() });
        return Ok(new { ticker = dto.Ticker.ToUpperInvariant() });
    }

    [HttpDelete("{ticker}")]
    public async Task<IActionResult> Remove(string ticker)
    {
        await watchlist.RemoveAsync(ticker.ToUpperInvariant());
        return NoContent();
    }
}
