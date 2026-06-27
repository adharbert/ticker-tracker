using Microsoft.AspNetCore.Mvc;
using NewsMarketAgent.Api.Services;

namespace NewsMarketAgent.Api.Controllers;

[ApiController]
[Route("api/ingest")]
public class IngestController(INewsIngestionService ingest) : ControllerBase
{
    [HttpPost("trigger")]
    public async Task<IActionResult> Trigger()
    {
        var status = await ingest.IngestLatestAsync();
        return Ok(new { status });
    }
}
