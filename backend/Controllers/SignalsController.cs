using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Models;
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/signals")]
public class SignalsController(ISignalService signals) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetSignals(
        [FromQuery] string? ticker,
        [FromQuery] int     limit = 20,
        [FromQuery] string? from  = null) =>
        Ok(await signals.GetAsync(ticker, limit, from));

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetById(Guid id)
    {
        var signal = await signals.GetByIdAsync(id);
        return signal is null ? NotFound() : Ok(signal);
    }

    // Called by Python agent — not browser-facing
    [HttpPost("callback")]
    public async Task<IActionResult> Callback([FromBody] SignalCallbackDto dto)
    {
        await signals.ProcessCallbackAsync(dto);
        return Ok();
    }
}
